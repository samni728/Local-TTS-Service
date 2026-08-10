import os
import asyncio
import logging
import json
import re
import secrets
import time
import hashlib
import hmac
import base64
import uuid
from io import BytesIO
from functools import wraps
import subprocess
import tempfile
import threading
from html import escape as html_escape

from dotenv import load_dotenv

load_dotenv()

from tls_config import (
    certificate_error_message,
    configure_tls_trust,
    is_certificate_verification_error,
)

TLS_TRUST_SOURCE = configure_tls_trust()

import edge_tts
import aiohttp
import urllib.parse
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for, Response
from flask_cors import CORS

from text_processing import pre_process_text, split_text_into_chunks
from voice_catalog import (
    build_voice_catalog,
    catalog_metadata,
    filter_voices,
    normalize_gender,
)

# --- 配置和初始化 ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
logger.info("TLS trust source: %s", TLS_TRUST_SOURCE)

# Microsoft Edge TTS API 配置
MICROSOFT_TTS_KEY = "oik6PdDdMnOXemTbwvMn9de/h9lFnfBaCWbGMMZqqoSaQaqUOqjVGm5NqsmjcBI1x+sS9ugjB55HEJWRiFXYFw=="
MICROSOFT_TTS_REGIONS = [
    "eastus", "eastus2", "southcentralus", "westus2", "westus3", "australiaeast", 
    "southeastasia", "northeurope", "swedencentral", "uksouth", "westeurope", 
    "centralus", "southafricanorth", "centralindia", "eastasia", "japaneast", 
    "koreacentral", "canadacentral", "francecentral", "germanywestcentral", 
    "italynorth", "norwayeast", "polandcentral", "switzerlandnorth", 
    "uaenorth", "brazilsouth", "centralusstage", "eastusstage", "eastus2stage", 
    "northcentralusstage", "southcentralusstage", "westusstage", "westus2stage", 
    "asia", "asiapacific", "australia", "brazil", "canada", "europe", "france", 
    "germany", "global", "india", "japan", "korea", "norway", "singapore", 
    "southafrica", "sweden", "switzerland", "uae", "uk", "unitedstates", 
    "unitedstateseuap", "eastasiastage", "southeastasiastage", "centraluseuap", 
    "eastus2euap", "westcentralus", "southafricawest", "australiacentral", 
    "australiacentral2", "australiasoutheast", "japanwest", "koreasouth", 
    "southindia", "westindia", "canadaeast", "francesouth", "germanynorth", 
    "norwaywest", "switzerlandwest", "ukwest", "uaecentral", "brazilsoutheast"
]
app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(24))

# --- 配置文件路径与全局变量 ---
CONFIG_FILE = 'config.json'
VOICES_LIST_FILE = os.path.join('tts_data', 'voices_list.txt')
LOCALES_MAP_FILE = os.path.join('tts_data', 'locales_map.json')
AZURE_VOICE_DOC_FILE = os.path.join('docs', 'Azure语音的语言和语音支持 - Foundry Tools - Microsoft Learn.md')
config = {}
ALL_VOICES = []
VOICE_INDEX = {}
SUPPORTED_LOCALES = {}
MAX_CONCURRENT_REQUESTS = 8
CHUNK_SIZE = 300
SYNC_CHUNKS = 1
OPENAI_VOICE_ALIASES = ("shimmer", "alloy", "fable", "onyx", "nova", "echo")
MICROSOFT_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=45, connect=10, sock_read=40)

# Global event loop for streaming tasks
STREAM_LOOP = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=STREAM_LOOP.run_forever, daemon=True)
_loop_thread.start()

async def generate_silence_bytes(duration: float = 0.2) -> bytes:
    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=24000:cl=mono",
        "-t",
        str(duration),
        "-q:a",
        "9",
        "-f",
        "mp3",
        "pipe:1",
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(
            f"FFmpeg failed to generate silence.\n{stderr.decode(errors='ignore')}"
        )
        return b""
    return stdout


async def generate_streaming_audio_async(
    text_chunks,
    voice,
    sync_chunks: int = 1,
    max_concurrent_requests: int | None = None,
    voice_style: str = "general",
    voice_role: str = "",
    style_degree: float = 1.0,
    speed: float = 1.0,
    pitch: float = 1.0,
):
    """Generate audio chunks and yield them in a hybrid streaming mode.

    The first few chunks are generated synchronously to provide an immediate
    playback experience. Remaining chunks are processed concurrently while
    ensuring chunks are yielded in order.
    """
    total_chunks = len(text_chunks)
    semaphore = asyncio.Semaphore(
        max_concurrent_requests or MAX_CONCURRENT_REQUESTS
    )
    buffers = [None] * (total_chunks + 1)
    results = [None] * (total_chunks + 1)
    ready_events = [None] + [asyncio.Event() for _ in range(total_chunks)]
    start_time = time.time()
    endpoint_task = None
    endpoint_lock = asyncio.Lock()
    # Number of chunks handled sequentially before switching to concurrency
    SYNC_CHUNKS = max(sync_chunks, 0)

    async def microsoft_tts(ssml_text: str) -> bytes:
        """Share one endpoint lookup across all streaming chunks in this request."""

        nonlocal endpoint_task
        async with endpoint_lock:
            if endpoint_task is None:
                endpoint_task = asyncio.create_task(get_microsoft_endpoint())
            current_task = endpoint_task
        try:
            endpoint = await current_task
        except Exception:
            async with endpoint_lock:
                if endpoint_task is current_task:
                    endpoint_task = None
            raise
        return await tts_with_microsoft_api(ssml_text, voice, endpoint=endpoint)

    async def process_chunk(idx: int, text: str):
        """Process a single text chunk with retry and concurrency control."""
        logger.info(f"[Streaming] Processing chunk {idx}/{total_chunks}")
        max_retries = 10
        chunk_start = time.time()
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"  [Task {idx}] Attempt {attempt + 1}/{max_retries} acquiring semaphore..."
                )
                async with semaphore:
                    logger.info(
                        f"  [Task {idx}] Acquired semaphore. Starting TTS request..."
                    )
                    # 计算速度和音调的百分比值
                    rate_percent = f"{int((speed - 1) * 100):+d}%"
                    pitch_percent = f"{int((pitch - 1) * 100):+d}Hz"
                    
                    buf = bytearray()
                    
                    expressive_request = (voice_style and voice_style != "general") or voice_role
                    if expressive_request:
                        ssml_text = generate_ssml(
                            text, voice, voice_style, voice_role, style_degree, speed, pitch
                        )
                        audio_data = await microsoft_tts(ssml_text)
                        buf.extend(audio_data)
                    else:
                        try:
                            communicate = edge_tts.Communicate(
                                text, voice, rate=rate_percent, pitch=pitch_percent
                            )
                            async for chunk_data in communicate.stream():
                                if chunk_data["type"] == "audio":
                                    buf.extend(chunk_data["data"])
                        except Exception as edge_error:
                            logger.warning(f"  [Task {idx}] edge_tts 库失败: {edge_error}")
                            logger.info(f"  [Task {idx}] 尝试使用 Microsoft API...")
                            ssml_text = generate_ssml(
                                text, voice, voice_style, voice_role, style_degree, speed, pitch
                            )
                            audio_data = await microsoft_tts(ssml_text)
                            buf.extend(audio_data)
                            logger.info(f"  [Task {idx}] Microsoft API 成功生成音频")
                if buf:
                    elapsed_time = time.time() - chunk_start
                    logger.info(
                        f"  [Task {idx}] Successfully generated in {elapsed_time:.2f}s after {attempt + 1} attempt(s)."
                    )
                    logger.info(
                        f"  [Task {idx}] Done. Total retry attempts: {attempt + 1}"
                    )
                    buffers[idx] = bytes(buf)
                    results[idx] = (True, attempt + 1, elapsed_time)
                    ready_events[idx].set()
                    break
                else:
                    raise edge_tts.NoAudioReceived("No audio was received (empty data).")
            except Exception as e:
                logger.warning(f"  [Task {idx}] Attempt {attempt + 1} failed: {e}")
                if attempt + 1 == max_retries:
                    elapsed_time = time.time() - chunk_start
                    logger.error(
                        f"  [Task {idx}] Failed after {max_retries} attempts. Giving up."
                    )
                    logger.info(
                        f"  [Task {idx}] Done. Total retry attempts: {attempt + 1}"
                    )
                    buffers[idx] = await generate_silence_bytes()
                    results[idx] = (False, attempt + 1, elapsed_time)
                    ready_events[idx].set()
                    break
                wait_time = min(2 ** attempt, 8)
                logger.info(f"  [Task {idx}] Retrying after {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)

    tasks = []
    next_idx = SYNC_CHUNKS + 1
    try:
        # Generate the warm-up chunks in order. Start the remaining work before
        # yielding the final warm-up chunk so playback and synthesis overlap.
        for idx, chunk in enumerate(text_chunks[:SYNC_CHUNKS], start=1):
            await process_chunk(idx, chunk)
            if idx == min(SYNC_CHUNKS, total_chunks):
                tasks = [
                    asyncio.create_task(process_chunk(i, remaining_chunk))
                    for i, remaining_chunk in enumerate(
                        text_chunks[SYNC_CHUNKS:], start=SYNC_CHUNKS + 1
                    )
                ]
            if buffers[idx] is not None:
                logger.info(f"Streaming chunk {idx}/{total_chunks} sent")
                yield buffers[idx]

        if not tasks and SYNC_CHUNKS == 0:
            tasks = [
                asyncio.create_task(process_chunk(i, chunk))
                for i, chunk in enumerate(text_chunks, start=1)
            ]

        while next_idx <= total_chunks:
            await ready_events[next_idx].wait()
            logger.info(f"Streaming chunk {next_idx}/{total_chunks} sent")
            yield buffers[next_idx]
            next_idx += 1
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time
        durations = [r[2] for r in results[1:] if r]
        total_attempts = sum(r[1] for r in results[1:] if r)
        avg_time = sum(durations) / len(durations) if durations else 0
        concurrency = (sum(durations) / total_time) if total_time > 0 else 0
        failed_indices = [idx for idx, r in enumerate(results[1:], start=1) if r and not r[0]]
        logger.info(
            f"All TTS tasks completed in {total_time:.2f}s. Average chunk time: {avg_time:.2f}s. Achieved concurrency: {concurrency:.2f}x"
        )
        logger.info(f"Total retry attempts across all tasks: {total_attempts}")
        logger.info("=" * 50)
        logger.info("TTS Request Summary:")
        logger.info(f"  - Total Chunks: {total_chunks}")
        logger.info(f"  - Successful Chunks: {total_chunks - len(failed_indices)}")
        logger.info(f"  - Failed Chunks: {len(failed_indices)}")
        if failed_indices:
            logger.warning(f"  - Indices of Failed Chunks: {failed_indices}")
        logger.info(f"  - Total Processing Time: {total_time:.2f}s")
        logger.info("=" * 50)

def generate_streaming_audio_sync(
    text_chunks,
    voice,
    sync_chunks: int = 1,
    max_concurrent_requests: int | None = None,
    voice_style: str = "general",
    voice_role: str = "",
    style_degree: float = 1.0,
    speed: float = 1.0,
    pitch: float = 1.0,
):
    async_iter = generate_streaming_audio_async(
        text_chunks, voice, sync_chunks, max_concurrent_requests, voice_style, voice_role, style_degree, speed, pitch
    ).__aiter__()

    def sync_gen():
        while True:
            future = asyncio.run_coroutine_threadsafe(async_iter.__anext__(), STREAM_LOOP)
            try:
                chunk = future.result()
            except StopAsyncIteration:
                break
            yield chunk

    return sync_gen()


# --- 数据加载与管理 ---
def load_config_from_file():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return None

def save_config_to_file(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def initialize_config():
    global config, MAX_CONCURRENT_REQUESTS, CHUNK_SIZE, SYNC_CHUNKS
    default_config = {
        "port": 5050,
        "api_token": "",
        "max_concurrent_requests": 8,
        "chunk_size": 300,
        "sync_chunks": 1,
        "sync_api_filtering": True,
        "default_cleaning_options": {
            "remove_markdown": True, "remove_emoji": True,
            "no_urls": True, "no_line_breaks": False, "custom_keywords": ""
        },
        "openai_voice_map": { "shimmer": "zh-CN-XiaoxiaoNeural", "alloy": "en-US-AriaNeural", "fable": "zh-CN-shaanxi-XiaoniNeural", "onyx": "en-US-ChristopherNeural", "nova": "en-US-AvaNeural", "echo": "zh-CN-YunyangNeural" },
        "openai_voice_presets": {},
        "custom_voices": {},
        "edge_user_id": "",
        "edge_client_trace_id": ""
    }
    loaded_config = load_config_from_file()
    if loaded_config is None:
        logger.info(f"'{CONFIG_FILE}' not found, creating a default one.")
        config = default_config
        save_config_to_file(config)
    else:
        updated = False
        for key, value in default_config.items():
            if key not in loaded_config:
                loaded_config[key] = value
                updated = True
        config = loaded_config
        if updated: save_config_to_file(config)
    presets = config.get("openai_voice_presets")
    if not isinstance(presets, dict):
        presets = {}
        config["openai_voice_presets"] = presets
    migrated_presets = False
    for alias, voice_name in config.get("openai_voice_map", {}).items():
        if alias not in presets and isinstance(voice_name, str) and voice_name:
            presets[alias] = {"voice": voice_name}
            migrated_presets = True
    if migrated_presets:
        save_config_to_file(config)
    # 设备 ID 与追踪 ID：若为空则生成一次并持久化
    if not config.get("edge_user_id"):
        config["edge_user_id"] = uuid.uuid4().hex[:16]
        save_config_to_file(config)
        logger.info(f"Generated persistent edge_user_id: {config['edge_user_id']}")
    if not config.get("edge_client_trace_id"):
        config["edge_client_trace_id"] = uuid.uuid4().hex
        save_config_to_file(config)
        logger.info("Generated persistent edge_client_trace_id (will be reused across requests)")
    MAX_CONCURRENT_REQUESTS = config.get("max_concurrent_requests", 8)
    CHUNK_SIZE = config.get("chunk_size", 300)
    SYNC_CHUNKS = config.get("sync_chunks", 1)
    logger.info(
        f"Configuration loaded. Port: {config.get('port')} - Max concurrent requests: {MAX_CONCURRENT_REQUESTS} - Chunk size: {CHUNK_SIZE} - Sync chunks: {SYNC_CHUNKS}"
    )

def parse_voices():
    global ALL_VOICES, VOICE_INDEX, SUPPORTED_LOCALES
    try:
        with open(VOICES_LIST_FILE, 'r', encoding='utf-8') as f: voices_raw_data = f.read()
        with open(LOCALES_MAP_FILE, 'r', encoding='utf-8') as f: locale_display_names = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}.")
        return

    try:
        with open(AZURE_VOICE_DOC_FILE, 'r', encoding='utf-8') as f:
            azure_document_text = f.read()
    except FileNotFoundError:
        azure_document_text = ""
        logger.warning("Azure voice capability document not found; using Edge voice list only.")

    ALL_VOICES = build_voice_catalog(
        voices_raw_data,
        locale_display_names,
        azure_document_text,
    )
    VOICE_INDEX = {voice["name"]: voice for voice in ALL_VOICES}
    SUPPORTED_LOCALES = {}
    for voice in ALL_VOICES:
        SUPPORTED_LOCALES.setdefault(voice["locale"], voice["locale_name"])
    metadata = catalog_metadata(ALL_VOICES)
    logger.info(
        "Voice catalog loaded: %s total, %s Edge-listed, %s Azure-documented.",
        metadata["total"],
        metadata["edge_available"],
        metadata["azure_documented"],
    )

# --- 认证装饰器 ---
def token_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        api_token = config.get('api_token')
        if api_token:
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '): return jsonify({"error": {"message": "Authorization header is missing or invalid."}}), 401
            provided_token = auth_header.split(' ')[1]
            if provided_token != api_token: return jsonify({"error": {"message": "Invalid API token."}}), 403
        return await f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        webui_password = os.environ.get('WEBUI_PASSWORD')
        if webui_password and not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 核心业务逻辑 ---
def _parse_bounded_float(data, keys, default, minimum, maximum):
    raw_value = next((data[key] for key in keys if key in data), default)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{keys[0]}' must be a number.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"'{keys[0]}' must be between {minimum} and {maximum}.")
    return value


def _parse_bounded_int(raw_value, name, default, minimum, maximum):
    if raw_value is None:
        raw_value = default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"'{name}' must be between {minimum} and {maximum}.")
    return value


def _get_openai_voice_preset(alias):
    if alias not in OPENAI_VOICE_ALIASES:
        return None
    raw_preset = config.get("openai_voice_presets", {}).get(alias)
    preset = dict(raw_preset) if isinstance(raw_preset, dict) else {}
    legacy_voice = config.get("openai_voice_map", {}).get(alias)
    if legacy_voice and not preset.get("voice"):
        preset["voice"] = legacy_voice
    return preset or None


def _preset_value(data, preset, keys, default, authoritative=False):
    """Resolve a setting from a saved preset and request data.

    Complete presets are authoritative by default so OpenAI SDKs that always
    send ``speed=1`` do not accidentally erase the WebUI setting. Advanced
    callers can opt in to request-side overrides with ``override_preset``.
    """

    if preset and authoritative and not data.get("override_preset", False):
        for key in keys:
            if key in preset:
                return preset[key]
    for key in keys:
        if key in data:
            return data[key]
    if preset:
        for key in keys:
            if key in preset:
                return preset[key]
    return default


def _resolve_voice(data, style="", role="", preset=None):
    requested_voice = data.get("voice")
    mapped_voice = (preset or {}).get("voice") or config.get('openai_voice_map', {}).get(requested_voice, requested_voice)
    requested_gender = data.get("gender")
    strict = bool(data.get("strict_capabilities", False))

    if not mapped_voice or mapped_voice == "auto":
        locale = data.get("locale")
        if not locale:
            raise ValueError("'locale' is required when voice is 'auto'.")
        candidates = filter_voices(
            ALL_VOICES,
            locale=locale,
            gender=requested_gender,
            style=style or None,
            role=role or None,
            voice_type=data.get("voice_type"),
            edge_available=bool(data.get("edge_available_only", False)),
        )
        if not candidates:
            raise ValueError("No voice matches the requested locale and capabilities.")
        mapped_voice = next(
            (voice["name"] for voice in candidates if voice["edge_available"]),
            candidates[0]["name"],
        )

    voice_info = VOICE_INDEX.get(mapped_voice)
    if strict and voice_info:
        if requested_gender and voice_info["gender"] != normalize_gender(requested_gender):
            raise ValueError(
                f"Voice '{mapped_voice}' has gender {voice_info['gender']}, not {normalize_gender(requested_gender)}."
            )
        if style and style not in voice_info["styles"]:
            supported = ", ".join(voice_info["styles"]) or "none"
            raise ValueError(f"Voice '{mapped_voice}' does not support style '{style}'. Supported: {supported}.")
        if role and role not in voice_info["roles"]:
            supported = ", ".join(voice_info["roles"]) or "none"
            raise ValueError(f"Voice '{mapped_voice}' does not support role '{role}'. Supported: {supported}.")
    return mapped_voice, voice_info


def _validate_and_build_openai_preset(data):
    voice_name = str(data.get("voice", "")).strip()
    if not voice_name:
        raise ValueError("'voice' is required.")

    style = str(data.get("style") or "general")
    role = str(data.get("role") or "")
    voice_info = VOICE_INDEX.get(voice_name)
    is_custom_voice = voice_name in config.get("custom_voices", {})
    if not voice_info and not is_custom_voice:
        raise ValueError(f"Voice '{voice_name}' was not found.")
    if voice_info:
        if style != "general" and style not in voice_info.get("styles", []):
            raise ValueError(f"Voice '{voice_name}' does not support style '{style}'.")
        if role and role not in voice_info.get("roles", []):
            raise ValueError(f"Voice '{voice_name}' does not support role '{role}'.")

    cleaning_options = data.get("cleaning_options", {})
    if not isinstance(cleaning_options, dict):
        raise ValueError("'cleaning_options' must be an object.")
    allowed_cleaning_keys = {
        "remove_markdown",
        "remove_emoji",
        "no_urls",
        "no_line_breaks",
        "custom_keywords",
    }
    cleaning_snapshot = {
        key: cleaning_options[key]
        for key in allowed_cleaning_keys
        if key in cleaning_options
    }

    return {
        "voice": voice_name,
        "style": style,
        "role": role,
        "style_degree": _parse_bounded_float(data, ("style_degree",), 1.0, 0.01, 2.0),
        "speed": _parse_bounded_float(data, ("speed",), 1.0, 0.25, 4.0),
        "pitch": _parse_bounded_float(data, ("pitch",), 1.0, 0.5, 1.5),
        "cleaning_options": cleaning_snapshot,
        "strict_capabilities": bool(voice_info),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def generate_ssml(text, voice, style="general", role="", style_degree=1.0, speed=1.0, pitch=1.0):
    """Generate Microsoft-compatible SSML for prosody, style, and role."""
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    escaped_text = '<break time="320ms"/>'.join(
        html_escape(paragraph, quote=False) for paragraph in paragraphs
    )
    escaped_voice = html_escape(voice, quote=True)
    voice_info = VOICE_INDEX.get(voice, {})
    xml_lang = voice_info.get("locale") or "-".join(voice.split("-")[:2])

    rate_percent = round((speed - 1) * 100)
    pitch_percent = round((pitch - 1) * 100)
    ssml_content = (
        f'<prosody rate="{rate_percent:+d}%" pitch="{pitch_percent:+d}%">'
        f'{escaped_text}</prosody>'
    )

    express_attributes = []
    if style and style != "general":
        express_attributes.append(f'style="{html_escape(style, quote=True)}"')
        express_attributes.append(f'styledegree="{style_degree:.2f}"')
    if role:
        express_attributes.append(f'role="{html_escape(role, quote=True)}"')
    if express_attributes:
        ssml_content = (
            f'<mstts:express-as {" ".join(express_attributes)}>'
            f'{ssml_content}</mstts:express-as>'
        )

    return (
        '<speak xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" version="1.0" '
        f'xml:lang="{html_escape(xml_lang, quote=True)}">'
        f'<voice name="{escaped_voice}">{ssml_content}</voice></speak>'
    )

# Microsoft Edge TTS API 辅助函数
async def get_microsoft_endpoint(client_session: aiohttp.ClientSession | None = None):
    """获取 Microsoft Edge TTS 端点信息"""
    owned_session = None
    try:
        # 首先调用 Microsoft Translator 端点获取真实的端点信息
        endpoint_url = "https://dev.microsofttranslator.com/apps/endpoint?api-version=1.0"
        client_id = config.get("edge_client_trace_id") or str(uuid.uuid4()).replace('-', '')
        user_id = config.get("edge_user_id") or "0f04d16a175c411e"  # 默认用户ID（回退）
        
        # 生成认证签名
        signature = await generate_microsoft_token(endpoint_url)
        
        # 尝试不同的语言和区域变体
        variants = [
            {"lang": "zh-Hans", "region": "zh-Hans-CN", "ver": "4.0.530a 5fe1dc6c"},
            {"lang": "en-US", "region": "en-US", "ver": "4.0.530a 5fe1dc6c"},
            {"lang": "en-US", "region": "en-US", "ver": "4.0.531a 5fe1dc6c"},
        ]
        
        if client_session is None:
            owned_session = aiohttp.ClientSession(timeout=MICROSOFT_HTTP_TIMEOUT)
            client_session = owned_session

        last_error = None
        for attempt in range(5):
            try:
                variant = variants[attempt % len(variants)]
                headers = {
                    "Accept-Language": variant["lang"],
                    "X-ClientVersion": variant["ver"],
                    "X-UserId": user_id,
                    "X-HomeGeographicRegion": variant["region"],
                    "X-ClientTraceId": client_id,
                    "X-MT-Signature": signature,
                    "User-Agent": "okhttp/4.5.0",
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": "0",
                    "Accept-Encoding": "gzip",
                }
                
                async with client_session.post(endpoint_url, headers=headers) as response:
                    if not response.ok:
                        raise Exception(f"HTTP {response.status}: {response.reason}")

                    data = await response.json()
                    return {"r": data["r"], "t": data["t"], "url": f"https://{data['r']}.tts.speech.microsoft.com/cognitiveservices/v1"}
                        
            except Exception as e:
                if is_certificate_verification_error(e):
                    raise RuntimeError(certificate_error_message(e)) from e
                last_error = e
                logger.warning(f"端点获取尝试 {attempt + 1} 失败: {e}")
                if attempt < 4:
                    await asyncio.sleep(1)
                continue
        
        raise Exception(f"获取端点失败，最后错误: {last_error}")
        
    except Exception as e:
        logger.error(f"获取 Microsoft 端点失败: {e}")
        raise
    finally:
        if owned_session is not None:
            await owned_session.close()

async def generate_microsoft_token(url_str):
    """生成 Microsoft Edge TTS 认证令牌"""
    try:
        # 使用 demo.js 中的认证逻辑
        url = url_str.split("://")[1]
        encoded_url = urllib.parse.quote(url, safe='')
        
        uuid_str = str(uuid.uuid4()).replace('-', '')
        from datetime import datetime
        formatted_date = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        bytes_to_sign = f"MSTranslatorAndroidApp{encoded_url}{formatted_date}{uuid_str}".lower()
        
        key_bytes = base64.b64decode(MICROSOFT_TTS_KEY)
        signature_bytes = hmac.new(key_bytes, bytes_to_sign.encode('utf-8'), hashlib.sha256).digest()
        signature = base64.b64encode(signature_bytes).decode('utf-8')
        
        # 使用 demo.js 的格式：MSTranslatorAndroidApp::signature::date::uuid
        return f"MSTranslatorAndroidApp::{signature}::{formatted_date}::{uuid_str}"
    except Exception as e:
        logger.error(f"生成 Microsoft 令牌失败: {e}")
        raise

async def tts_with_microsoft_api(
    ssml_text,
    voice,
    output_format="audio-24khz-48kbitrate-mono-mp3",
    endpoint=None,
    client_session: aiohttp.ClientSession | None = None,
):
    """使用 Microsoft Edge TTS API 直接生成音频"""
    owned_session = None
    try:
        if client_session is None:
            owned_session = aiohttp.ClientSession(timeout=MICROSOFT_HTTP_TIMEOUT)
            client_session = owned_session
        if endpoint is None:
            endpoint = await get_microsoft_endpoint(client_session)
        
        headers = {
            "Authorization": endpoint["t"],
            "Content-Type": "application/ssml+xml",
            "User-Agent": "okhttp/4.5.0",
            "X-Microsoft-OutputFormat": output_format,
        }
        
        async with client_session.post(endpoint["url"], headers=headers, data=ssml_text) as response:
            if not response.ok:
                error_text = await response.text()
                raise Exception(f"Microsoft TTS API error: {response.status} {error_text}")

            return await response.read()
                
    except Exception as e:
        logger.error(f"Microsoft TTS API 调用失败: {e}")
        raise
    finally:
        if owned_session is not None:
            await owned_session.close()

async def text_to_speech_with_retry(semaphore, chunk_index, text_chunk, voice, temp_dir, voice_style="general", voice_role="", style_degree=1.0, speed=1.0, pitch=1.0):
    task_start_time = time.time()
    max_retries = 10
    logger.info(f"  [Task {chunk_index+1}] Starting processing for chunk: '{text_chunk[:30]}...'")
    for attempt in range(max_retries):
        try:
            logger.info(
                f"  [Task {chunk_index+1}] Attempt {attempt + 1}/{max_retries} acquiring semaphore..."
            )
            async with semaphore:
                logger.info(f"  [Task {chunk_index+1}] Acquired semaphore. Starting TTS request...")
                
                # 计算速度和音调的百分比值
                rate_percent = f"{int((speed - 1) * 100):+d}%"
                pitch_percent = f"{int((pitch - 1) * 100):+d}Hz"
                
                temp_file_path = os.path.join(temp_dir, f"segment_{chunk_index}.mp3")
                
                expressive_request = (voice_style and voice_style != "general") or voice_role
                if expressive_request:
                    ssml_text = generate_ssml(
                        text_chunk, voice, voice_style, voice_role, style_degree, speed, pitch
                    )
                    audio_data = await tts_with_microsoft_api(ssml_text, voice)
                    with open(temp_file_path, "wb") as temp_file:
                        temp_file.write(audio_data)
                else:
                    try:
                        communicate = edge_tts.Communicate(
                            text_chunk, voice, rate=rate_percent, pitch=pitch_percent
                        )
                        with open(temp_file_path, "wb") as temp_file:
                            async for chunk in communicate.stream():
                                if chunk["type"] == "audio":
                                    temp_file.write(chunk["data"])
                    except Exception as edge_error:
                        logger.warning(f"  [Task {chunk_index+1}] edge_tts 库失败: {edge_error}")
                        logger.info(f"  [Task {chunk_index+1}] 尝试使用 Microsoft API...")
                        ssml_text = generate_ssml(
                            text_chunk, voice, voice_style, voice_role, style_degree, speed, pitch
                        )
                        audio_data = await tts_with_microsoft_api(ssml_text, voice)
                        with open(temp_file_path, "wb") as temp_file:
                            temp_file.write(audio_data)
                        logger.info(f"  [Task {chunk_index+1}] Microsoft API 成功生成音频")
            if os.path.getsize(temp_file_path) > 0:
                elapsed_time = time.time() - task_start_time
                logger.info(
                    f"  [Task {chunk_index+1}] Successfully generated in {elapsed_time:.2f}s after {attempt + 1} attempt(s)."
                )
                logger.info(f"  [Task {chunk_index+1}] Done. Total retry attempts: {attempt + 1}")
                return temp_file_path, attempt + 1, elapsed_time
            else:
                raise edge_tts.NoAudioReceived("No audio was received (empty file).")
        except Exception as e:
            logger.warning(f"  [Task {chunk_index+1}] Attempt {attempt + 1} failed: {e}")
            if attempt + 1 == max_retries:
                elapsed_time = time.time() - task_start_time
                logger.error(
                    f"  [Task {chunk_index+1}] Failed after {max_retries} attempts. Giving up."
                )
                logger.info(f"  [Task {chunk_index+1}] Done. Total retry attempts: {attempt + 1}")
                return None, attempt + 1, elapsed_time
            wait_time = min(2 ** attempt, 8)
            logger.info(f"  [Task {chunk_index+1}] Retrying after {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)

async def run_tts(
    text_chunks,
    voice,
    temp_dir,
    max_concurrent_requests: int | None = None,
    voice_style: str = "general",
    voice_role: str = "",
    style_degree: float = 1.0,
    speed: float = 1.0,
    pitch: float = 1.0,
):
    limit = max_concurrent_requests or MAX_CONCURRENT_REQUESTS
    logger.info(
        f"[Step 2/4] Starting TTS generation with concurrency limit: {limit}..."
    )
    semaphore = asyncio.Semaphore(limit)
    start_time = time.time()
    tasks = [text_to_speech_with_retry(semaphore, i, chunk, voice, temp_dir, voice_style, voice_role, style_degree, speed, pitch) for i, chunk in enumerate(text_chunks)]
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    durations = [r[2] for r in results if r is not None]
    total_attempts = sum(r[1] for r in results if r is not None)
    avg_time = sum(durations) / len(durations) if durations else 0
    concurrency = (sum(durations) / total_time) if total_time > 0 else 0
    logger.info(
        f"All TTS tasks completed in {total_time:.2f}s. Average chunk time: {avg_time:.2f}s. Achieved concurrency: {concurrency:.2f}x"
    )
    logger.info(f"Total retry attempts across all tasks: {total_attempts}")
    return [r[0] if r else None for r in results]

async def text_to_speech_official_first(
    semaphore,
    chunk_index,
    text_chunk,
    voice,
    temp_dir,
    voice_style="general",
    voice_role="",
    style_degree=1.0,
    speed=1.0,
    pitch=1.0,
    endpoint=None,
    client_session=None,
):
    task_start_time = time.time()
    max_retries = 5
    logger.info(f"  [Official/Task {chunk_index+1}] Starting processing for chunk: '{text_chunk[:30]}...'")
    for attempt in range(max_retries):
        try:
            logger.info(
                f"  [Official/Task {chunk_index+1}] Attempt {attempt + 1}/{max_retries} acquiring semaphore..."
            )
            async with semaphore:
                logger.info(f"  [Official/Task {chunk_index+1}] Acquired semaphore. Starting Microsoft API request...")
                temp_file_path = os.path.join(temp_dir, f"segment_{chunk_index}.mp3")
                ssml_text = generate_ssml(text_chunk, voice, voice_style, voice_role, style_degree, speed, pitch)
                audio_data = await tts_with_microsoft_api(
                    ssml_text,
                    voice,
                    endpoint=endpoint,
                    client_session=client_session,
                )
                with open(temp_file_path, "wb") as temp_file:
                    temp_file.write(audio_data)
            if os.path.getsize(temp_file_path) > 0:
                elapsed_time = time.time() - task_start_time
                logger.info(
                    f"  [Official/Task {chunk_index+1}] Successfully generated in {elapsed_time:.2f}s after {attempt + 1} attempt(s)."
                )
                logger.info(f"  [Official/Task {chunk_index+1}] Done. Total retry attempts: {attempt + 1}")
                return temp_file_path, attempt + 1, elapsed_time
            else:
                raise Exception("Official API returned empty file.")
        except Exception as e:
            logger.warning(f"  [Official/Task {chunk_index+1}] Attempt {attempt + 1} failed: {e}")
            if attempt + 1 == max_retries:
                elapsed_time = time.time() - task_start_time
                logger.error(
                    f"  [Official/Task {chunk_index+1}] Failed after {max_retries} attempts. Giving up."
                )
                logger.info(f"  [Official/Task {chunk_index+1}] Done. Total retry attempts: {attempt + 1}")
                return None, attempt + 1, elapsed_time
            wait_time = min(2 ** attempt, 8)
            logger.info(f"  [Official/Task {chunk_index+1}] Retrying after {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)

async def run_tts_official_first(
    text_chunks,
    voice,
    temp_dir,
    max_concurrent_requests: int | None = None,
    voice_style: str = "general",
    voice_role: str = "",
    style_degree: float = 1.0,
    speed: float = 1.0,
    pitch: float = 1.0,
):
    limit = max_concurrent_requests or MAX_CONCURRENT_REQUESTS
    logger.info(
        f"[Step 2/4] Starting OFFICIAL-FIRST TTS generation with concurrency limit: {limit}..."
    )
    semaphore = asyncio.Semaphore(limit)
    start_time = time.time()
    async with aiohttp.ClientSession(timeout=MICROSOFT_HTTP_TIMEOUT) as client_session:
        endpoint = await get_microsoft_endpoint(client_session)
        tasks = [
            text_to_speech_official_first(
                semaphore,
                i,
                chunk,
                voice,
                temp_dir,
                voice_style,
                voice_role,
                style_degree,
                speed,
                pitch,
                endpoint,
                client_session,
            )
            for i, chunk in enumerate(text_chunks)
        ]
        results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    durations = [r[2] for r in results if r is not None]
    total_attempts = sum(r[1] for r in results if r is not None)
    avg_time = sum(durations) / len(durations) if durations else 0
    concurrency = (sum(durations) / total_time) if total_time > 0 else 0
    logger.info(
        f"All OFFICIAL-FIRST TTS tasks completed in {total_time:.2f}s. Average chunk time: {avg_time:.2f}s. Achieved concurrency: {concurrency:.2f}x"
    )
    logger.info(f"Total retry attempts across all OFFICIAL-FIRST tasks: {total_attempts}")
    return [r[0] if r else None for r in results]

# --- Flask 路由和 API ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', locales=SUPPORTED_LOCALES)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    webui_password = os.environ.get('WEBUI_PASSWORD')
    if not webui_password: return redirect(url_for('index'))
    if session.get('logged_in'): return redirect(url_for('index'))
    if request.method == 'POST':
        if request.form.get('password') == webui_password:
            session['logged_in'] = True
            next_url = request.form.get('next')
            if next_url and (next_url.startswith('/') or next_url.startswith('http')): return redirect(next_url)
            return redirect(url_for('index'))
        else:
            error = '密码错误，请重试。'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/v1/audio/all_voices', methods=['GET'])
@login_required
def get_all_voices():
    filtered = filter_voices(
        ALL_VOICES,
        locale=request.args.get("locale"),
        gender=request.args.get("gender"),
        style=request.args.get("style"),
        role=request.args.get("role"),
        voice_type=request.args.get("voice_type"),
        supports_style=request.args.get("supports_style", "").lower() in {"1", "true", "yes"},
        supports_role=request.args.get("supports_role", "").lower() in {"1", "true", "yes"},
        edge_available=request.args.get("edge_available", "").lower() in {"1", "true", "yes"},
        query=request.args.get("q"),
    )
    return jsonify(filtered)


@app.route('/v1/voices', methods=['GET'])
@token_required
async def list_voice_catalog():
    filtered = filter_voices(
        ALL_VOICES,
        locale=request.args.get("locale"),
        gender=request.args.get("gender"),
        style=request.args.get("style"),
        role=request.args.get("role"),
        voice_type=request.args.get("voice_type"),
        supports_style=request.args.get("supports_style", "").lower() in {"1", "true", "yes"},
        supports_role=request.args.get("supports_role", "").lower() in {"1", "true", "yes"},
        edge_available=request.args.get("edge_available", "").lower() in {"1", "true", "yes"},
        query=request.args.get("q"),
    )
    return jsonify({"object": "list", "data": filtered, "meta": catalog_metadata(filtered)})


@app.route('/v1/voices/<path:voice_name>', methods=['GET'])
@token_required
async def get_voice_capabilities(voice_name):
    voice = VOICE_INDEX.get(voice_name)
    if not voice:
        return jsonify({"error": {"message": f"Voice '{voice_name}' was not found."}}), 404
    return jsonify(voice)

@app.route('/v1/config', methods=['GET'])
@login_required
def get_config():
    logger.info(
        f"[CONFIG LOADED] Current config: Port={config.get('port')}, ChunkSize={config.get('chunk_size')}, SyncChunks={config.get('sync_chunks')}, Concurrency={config.get('max_concurrent_requests')}"
    )
    return jsonify(config)

@app.route('/v1/config', methods=['POST'])
@login_required
def update_config():
    global config, MAX_CONCURRENT_REQUESTS, CHUNK_SIZE, SYNC_CHUNKS
    try:
        new_data = request.get_json()
        if not isinstance(new_data, dict):
            return jsonify({"error": "Invalid data format"}), 400
        required_keys = [
            'port',
            'api_token',
            'openai_voice_map',
            'max_concurrent_requests',
            'chunk_size',
            'sync_chunks',
            'sync_api_filtering',
            'default_cleaning_options',
        ]
        if not all(k in new_data for k in required_keys):
            return jsonify({"error": "Invalid data format"}), 400

        try:
            new_data["port"] = _parse_bounded_int(new_data.get("port"), "port", 5050, 1, 65535)
            new_data["chunk_size"] = _parse_bounded_int(
                new_data.get("chunk_size"), "chunk_size", 300, 50, 2000
            )
            new_data["sync_chunks"] = _parse_bounded_int(
                new_data.get("sync_chunks"), "sync_chunks", 1, 0, 20
            )
            new_data["max_concurrent_requests"] = _parse_bounded_int(
                new_data.get("max_concurrent_requests"),
                "max_concurrent_requests",
                8,
                1,
                32,
            )
        except ValueError as validation_error:
            return jsonify({"error": str(validation_error)}), 400

        changed_msgs = []
        field_names = {
            'port': 'Port',
            'chunk_size': 'ChunkSize',
            'sync_chunks': 'SyncChunks',
            'max_concurrent_requests': 'Concurrency',
            'api_token': 'ApiToken',
        }
        for key in ['port', 'chunk_size', 'sync_chunks', 'max_concurrent_requests', 'api_token']:
            old_val = config.get(key)
            new_val = new_data.get(key)
            if old_val != new_val:
                field = field_names.get(key, key)
                changed_msgs.append(
                    f"{field} changed: {old_val} \u2192 {new_val}"
                )

        config.update(new_data)
        MAX_CONCURRENT_REQUESTS = config.get("max_concurrent_requests", 8)
        CHUNK_SIZE = config.get("chunk_size", 300)
        SYNC_CHUNKS = config.get("sync_chunks", 1)
        save_config_to_file(config)

        if changed_msgs:
            for msg in changed_msgs:
                logger.info(f"[CONFIG UPDATED] {msg}")
        else:
            logger.info("[CONFIG NO CHANGE]")
        return jsonify({"message": "设置已保存。"})
    except Exception as e:
        logger.error(f"Error updating config: {e}", exc_info=True)
        return jsonify({"error": "更新配置时发生内部错误。"}), 500


@app.route('/v1/openai-voice-presets', methods=['GET'])
@login_required
def get_openai_voice_presets():
    return jsonify({
        alias: _get_openai_voice_preset(alias)
        for alias in OPENAI_VOICE_ALIASES
    })


@app.route('/v1/openai-voice-presets/<alias>', methods=['POST'])
@login_required
def save_openai_voice_preset(alias):
    if alias not in OPENAI_VOICE_ALIASES:
        return jsonify({"error": "Unsupported OpenAI voice alias."}), 400
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400
        preset = _validate_and_build_openai_preset(data)
        config.setdefault("openai_voice_presets", {})[alias] = preset
        config.setdefault("openai_voice_map", {})[alias] = preset["voice"]
        save_config_to_file(config)
        logger.info(
            "OpenAI voice preset '%s' saved: voice=%s, style=%s, role=%s, speed=%s, pitch=%s",
            alias,
            preset["voice"],
            preset["style"],
            preset["role"] or "default",
            preset["speed"],
            preset["pitch"],
        )
        return jsonify({
            "message": f"OpenAI 音色 {alias} 已保存。",
            "alias": alias,
            "preset": preset,
        })
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        logger.error("Failed to save OpenAI voice preset: %s", error, exc_info=True)
        return jsonify({"error": "保存 OpenAI 音色预设失败。"}), 500

@app.route('/v1/custom-voices', methods=['GET'])
@login_required
def get_custom_voices():
    """获取自定义音色列表"""
    return jsonify(config.get('custom_voices', {}))

@app.route('/v1/custom-voices', methods=['POST'])
@login_required
def add_custom_voice():
    """添加自定义音色"""
    try:
        data = request.get_json()
        voice_name = data.get('voice_name', '').strip()
        display_name = data.get('display_name', '').strip()
        
        if not voice_name:
            return jsonify({"error": "音色名称不能为空"}), 400
            
        if not display_name:
            display_name = voice_name
            
        # 添加到自定义音色列表
        custom_voices = config.get('custom_voices', {})
        custom_voices[voice_name] = display_name
        config['custom_voices'] = custom_voices
        save_config_to_file(config)
        
        return jsonify({"message": "自定义音色添加成功", "voice_name": voice_name, "display_name": display_name})
    except Exception as e:
        logger.error(f"Error adding custom voice: {e}")
        return jsonify({"error": "添加自定义音色失败"}), 500

@app.route('/v1/custom-voices/<voice_name>', methods=['DELETE'])
@login_required
def delete_custom_voice(voice_name):
    """删除自定义音色"""
    try:
        custom_voices = config.get('custom_voices', {})
        if voice_name in custom_voices:
            del custom_voices[voice_name]
            config['custom_voices'] = custom_voices
            save_config_to_file(config)
            return jsonify({"message": "自定义音色删除成功"})
        else:
            return jsonify({"error": "自定义音色不存在"}), 404
    except Exception as e:
        logger.error(f"Error deleting custom voice: {e}")
        return jsonify({"error": "删除自定义音色失败"}), 500

@app.route('/v1/models', methods=['GET'])
@token_required
async def list_models():
    client_ip = request.remote_addr or 'unknown'
    logger.info(f"[INFO] - /v1/models requested by {client_ip}")

    voice_map = config.get('openai_voice_map', {})
    models = [
        {
            "id": f"tts-1-{name}",
            "object": "model",
            "owned_by": "local-tts",
        }
        for name in voice_map.keys()
    ]
    models.append({"id": "tts-1", "object": "model", "owned_by": "local-tts"})
    return jsonify({"object": "list", "data": models})

@app.route('/v1/audio/speech', methods=['POST'])
@token_required
async def generate_speech():
    request_start_time = time.time()
    logger.info("="*50)
    logger.info("Received new TTS request.")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": {"message": "Request body must be a JSON object."}}), 400

            text = data.get("input")
            stream_enabled = bool(data.get("stream", False))

            requested_alias = data.get("voice")
            voice_preset = _get_openai_voice_preset(requested_alias)
            preset_is_complete = bool(
                voice_preset
                and any(
                    key in voice_preset
                    for key in ("style", "role", "style_degree", "speed", "pitch", "cleaning_options")
                )
            )
            voice_style = str(
                _preset_value(
                    data,
                    voice_preset,
                    ("style", "emotion"),
                    "general",
                    authoritative=preset_is_complete,
                )
                or "general"
            )
            voice_role = str(
                _preset_value(
                    data,
                    voice_preset,
                    ("role",),
                    "",
                    authoritative=preset_is_complete,
                )
                or ""
            )
            effective_settings = {
                "style_degree": _preset_value(
                    data,
                    voice_preset,
                    ("style_degree", "styleDegree", "emotion_intensity"),
                    1.0,
                    authoritative=preset_is_complete,
                ),
                "speed": _preset_value(
                    data,
                    voice_preset,
                    ("speed",),
                    1.0,
                    authoritative=preset_is_complete,
                ),
                "pitch": _preset_value(
                    data,
                    voice_preset,
                    ("pitch",),
                    1.0,
                    authoritative=preset_is_complete,
                ),
            }
            try:
                style_degree = _parse_bounded_float(
                    effective_settings,
                    ("style_degree",),
                    1.0,
                    0.01,
                    2.0,
                )
                speed = _parse_bounded_float(effective_settings, ("speed",), 1.0, 0.25, 4.0)
                pitch = _parse_bounded_float(effective_settings, ("pitch",), 1.0, 0.5, 1.5)
                resolved_data = dict(data)
                if voice_preset and "strict_capabilities" in voice_preset:
                    resolved_data["strict_capabilities"] = voice_preset["strict_capabilities"]
                final_voice, voice_info = _resolve_voice(
                    resolved_data,
                    style="" if voice_style == "general" else voice_style,
                    role=voice_role,
                    preset=voice_preset,
                )
            except ValueError as validation_error:
                return jsonify({"error": {"message": str(validation_error)}}), 400
            
            # 核心逻辑：决定使用哪套过滤规则
            preset_cleaning = (voice_preset or {}).get("cleaning_options")
            if (
                isinstance(preset_cleaning, dict)
                and not (data.get("override_preset", False) and "cleaning_options" in data)
            ):
                cleaning_options = preset_cleaning
                logger.info("Using cleaning options saved in OpenAI voice preset '%s'.", requested_alias)
            elif config.get('sync_api_filtering', False):
                cleaning_options = config.get('default_cleaning_options', {})
                logger.info("API filtering sync is ON. Using default cleaning options from config.")
            else:
                cleaning_options = data.get("cleaning_options", {})
                logger.info("API filtering sync is OFF. Using cleaning options from request body (if any).")
            
            if not isinstance(text, str) or not text.strip():
                return jsonify({"error": {"message": "Parameter 'input' must be a non-empty string."}}), 400

            logger.info("[Step 1/4] Pre-processing text...")
            processed_text = pre_process_text(text, cleaning_options)
            if processed_text is None:
                logger.error("\u274c processed_text is None!\uFF01\u8BF7\u68C0\u67E5\u524D\u9762\u7684\u6E05\u6D17\u903B\u8F91")

            # Optional request-level tuning with defensive limits. Zero must not
            # be treated as "missing", especially for sync_chunks.
            chunk_size_raw = data.get("chunk_size")
            if chunk_size_raw is None:
                chunk_size_raw = request.args.get("chunk_size")
            if chunk_size_raw is None:
                chunk_size_raw = request.args.get("max_chunk_len")

            sync_chunks_raw = data.get("sync_chunks")
            if sync_chunks_raw is None:
                sync_chunks_raw = request.args.get("sync_chunks")

            concurrency_raw = data.get("max_concurrent_requests")
            if concurrency_raw is None:
                concurrency_raw = request.args.get("max_concurrent_requests")
            try:
                chunk_size_override = _parse_bounded_int(
                    chunk_size_raw, "chunk_size", CHUNK_SIZE, 50, 2000
                )
                sync_chunks = _parse_bounded_int(
                    sync_chunks_raw, "sync_chunks", SYNC_CHUNKS, 0, 20
                )
                max_concurrent_requests_override = _parse_bounded_int(
                    concurrency_raw,
                    "max_concurrent_requests",
                    MAX_CONCURRENT_REQUESTS,
                    1,
                    32,
                )
            except ValueError as validation_error:
                return jsonify({"error": {"message": str(validation_error)}}), 400

            max_chunk_len = chunk_size_override

            text_chunks = split_text_into_chunks(processed_text, max_chunk_len=max_chunk_len)
            if not text_chunks:
                return jsonify({"error": {"message": "Input text is empty."}}), 400

            for idx, chunk in enumerate(text_chunks, 1):
                logger.info(f"Chunk {idx} length: {len(chunk)}")

            if stream_enabled:
                logger.info("Streaming mode enabled. Sending chunks as they are generated...")

                response = Response(
                    generate_streaming_audio_sync(
                        text_chunks,
                        final_voice,
                        sync_chunks,
                        max_concurrent_requests_override,
                        voice_style,
                        voice_role,
                        style_degree,
                        speed,
                        pitch,
                    ),
                    content_type="audio/mpeg",
                )
                response.headers["X-TTS-Voice"] = final_voice
                response.headers["X-TTS-Chunks"] = str(len(text_chunks))
                response.headers["X-TTS-Chunk-Size"] = str(max_chunk_len)
                if voice_style and voice_style != "general":
                    response.headers["X-TTS-Style"] = voice_style
                if voice_role:
                    response.headers["X-TTS-Role"] = voice_role
                if voice_preset:
                    response.headers["X-TTS-Preset"] = str(requested_alias)
                return response

            # 非流式：优先使用官方 API（稳定性优先）
            try:
                temp_file_paths = await run_tts_official_first(
                    text_chunks,
                    final_voice,
                    temp_dir,
                    max_concurrent_requests_override,
                    voice_style,
                    voice_role,
                    style_degree,
                    speed,
                    pitch,
                )
            except Exception as upstream_error:
                logger.error("Microsoft TTS request setup failed: %s", upstream_error)
                return jsonify({
                    "error": {
                        "message": "Microsoft TTS upstream is unavailable. Check connectivity and TLS trust settings."
                    }
                }), 502
            if not any(temp_file_paths):
                logger.error("All TTS chunks failed; returning an upstream error instead of silent audio.")
                return jsonify({
                    "error": {
                        "message": "All TTS chunks failed. Check Microsoft connectivity and TLS trust settings."
                    }
                }), 502
            generation_duration = time.time() - request_start_time
            logger.info(f"Concurrent generation finished in {generation_duration:.2f}s.")
            
            logger.info("[Step 3/4] Stitching audio segments using FFmpeg...")
            stitching_start_time = time.time()
            list_file_path = os.path.join(temp_dir, "file_list.txt")
            failed_chunks_indices = []
            with open(list_file_path, "w", encoding='utf-8') as f:
                for i, path in enumerate(temp_file_paths):
                    if path: f.write(f"file '{os.path.basename(path)}'\n")
                    else:
                        silent_path = os.path.join(temp_dir, f"silent_{i}.mp3")
                        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.2", "-q:a", "9", silent_path], check=True, capture_output=True)
                        f.write(f"file '{os.path.basename(silent_path)}'\n")
                        failed_chunks_indices.append(i + 1)
            output_file_path = os.path.join(temp_dir, "final_output.mp3")
            ffmpeg_command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file_path, "-c", "copy", output_file_path]
            process = await asyncio.create_subprocess_exec(*ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logger.error(f"FFmpeg failed with return code {process.returncode}.\nFFmpeg stderr:\n{stderr.decode(errors='ignore')}")
                return jsonify({"error": {"message": "Failed to stitch audio files. Check server logs."}}), 500
            stitching_duration = time.time() - stitching_start_time
            logger.info(f"Stitching complete in {stitching_duration:.2f}s.")

            logger.info("[Step 4/4] Exporting final audio and sending response...")
            with open(output_file_path, 'rb') as f: final_audio_data = f.read()
            final_audio_stream = BytesIO(final_audio_data)

            total_request_duration = time.time() - request_start_time
            logger.info("="*50)
            logger.info("TTS Request Summary:")
            logger.info(f"  - Total Chunks: {len(text_chunks)}")
            logger.info(f"  - Successful Chunks: {len(text_chunks) - len(failed_chunks_indices)}")
            logger.info(f"  - Failed Chunks: {len(failed_chunks_indices)}")
            if failed_chunks_indices: logger.warning(f"  - Indices of Failed Chunks: {failed_chunks_indices}")
            logger.info(f"  - Total Processing Time: {total_request_duration:.2f}s")
            logger.info("="*50)
            
            response = send_file(final_audio_stream, mimetype='audio/mpeg', as_attachment=False)
            response.headers["X-TTS-Voice"] = final_voice
            response.headers["X-TTS-Chunks"] = str(len(text_chunks))
            response.headers["X-TTS-Chunk-Size"] = str(max_chunk_len)
            if voice_style and voice_style != "general":
                response.headers["X-TTS-Style"] = voice_style
            if voice_role:
                response.headers["X-TTS-Role"] = voice_role
            if voice_preset:
                response.headers["X-TTS-Preset"] = str(requested_alias)
            if voice_info and not voice_info["edge_available"]:
                response.headers["X-TTS-Catalog-Source"] = "azure-document"
            return response
        except Exception as e:
            logger.error(f"An unexpected error occurred in generate_speech: {e}", exc_info=True)
            return jsonify({"error": {"message": "Internal server error."}}), 500

# --- 应用启动 ---
if __name__ == '__main__':
    initialize_config()
    parse_voices()
    
    port = int(os.environ.get('TTS_INTERNAL_PORT', config.get('port', 5050)))
    logger.info(f"Server starting on http://0.0.0.0:{port}")
    if os.environ.get('WEBUI_PASSWORD'):
        logger.info("✅ WebUI password protection is enabled.")
    else:
        logger.warning("⚠️ WebUI is open to public access. Set WEBUI_PASSWORD in .env to enable protection.")
    if config.get('api_token'):
        logger.info(f"API Token is configured. Use 'Authorization: Bearer <Your-Token>' for API calls.")
    else:
        logger.warning("API Token is not configured. The API for TTS is open to public access.")
        
    debug_enabled = os.environ.get('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes'}
    app.run(host='0.0.0.0', port=port, debug=debug_enabled)
