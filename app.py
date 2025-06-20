import os
import asyncio
import logging
import json
import re
import secrets
import time
from io import BytesIO
from collections import defaultdict
from functools import wraps
import subprocess
import tempfile
import threading

import edge_tts
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for, Response
from flask_cors import CORS
from dotenv import load_dotenv
import emoji

# --- 配置和初始化 ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(24))

# --- 配置文件路径与全局变量 ---
CONFIG_FILE = 'config.json'
VOICES_LIST_FILE = os.path.join('tts_data', 'voices_list.txt')
LOCALES_MAP_FILE = os.path.join('tts_data', 'locales_map.json')
config = {}
ALL_VOICES = []
SUPPORTED_LOCALES = {}
MAX_CONCURRENT_REQUESTS = 20
CHUNK_SIZE = 300
SYNC_CHUNKS = 1

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
    start_time = time.time()
    # Number of chunks handled sequentially before switching to concurrency
    SYNC_CHUNKS = max(sync_chunks, 0)

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
                    communicate = edge_tts.Communicate(text, voice)
                    buf = bytearray()
                    async for chunk_data in communicate.stream():
                        if chunk_data["type"] == "audio":
                            buf.extend(chunk_data["data"])
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
                    break
                wait_time = min(2 ** attempt, 8)
                logger.info(f"  [Task {idx}] Retrying after {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)

    # --- Step 1: process the first few chunks synchronously ---
    for idx, chunk in enumerate(text_chunks[:SYNC_CHUNKS], start=1):
        await process_chunk(idx, chunk)
        if buffers[idx] is not None:
            logger.info(f"Streaming chunk {idx}/{total_chunks} sent")
            yield buffers[idx]

    # --- Step 2: launch concurrent tasks for the remaining chunks ---
    tasks = [
        asyncio.create_task(process_chunk(i, chunk))
        for i, chunk in enumerate(text_chunks[SYNC_CHUNKS:], start=SYNC_CHUNKS + 1)
    ]

    next_idx = SYNC_CHUNKS + 1
    try:
        while next_idx <= total_chunks:
            if buffers[next_idx] is not None:
                logger.info(f"Streaming chunk {next_idx}/{total_chunks} sent")
                yield buffers[next_idx]
                next_idx += 1
            else:
                await asyncio.sleep(0.05)
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
):
    async_iter = generate_streaming_audio_async(
        text_chunks, voice, sync_chunks, max_concurrent_requests
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
        "max_concurrent_requests": 20,
        "chunk_size": 300,
        "sync_chunks": 1,
        "sync_api_filtering": True,
        "default_cleaning_options": {
            "remove_markdown": True, "remove_emoji": True,
            "no_urls": True, "no_line_breaks": False, "custom_keywords": ""
        },
        "openai_voice_map": { "shimmer": "zh-CN-XiaoxiaoNeural", "alloy": "en-US-AriaNeural", "fable": "zh-CN-shaanxi-XiaoniNeural", "onyx": "en-US-ChristopherNeural", "nova": "en-US-AvaNeural", "echo": "zh-CN-YunyangNeural" }
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
    MAX_CONCURRENT_REQUESTS = config.get("max_concurrent_requests", 20)
    CHUNK_SIZE = config.get("chunk_size", 300)
    SYNC_CHUNKS = config.get("sync_chunks", 1)
    logger.info(
        f"Configuration loaded. Port: {config.get('port')} - Max concurrent requests: {MAX_CONCURRENT_REQUESTS} - Chunk size: {CHUNK_SIZE} - Sync chunks: {SYNC_CHUNKS}"
    )

def parse_voices():
    global ALL_VOICES, SUPPORTED_LOCALES
    try:
        with open(VOICES_LIST_FILE, 'r', encoding='utf-8') as f: voices_raw_data = f.read()
        with open(LOCALES_MAP_FILE, 'r', encoding='utf-8') as f: locale_display_names = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}.")
        return

    lines = voices_raw_data.strip().split('\n')
    locales_with_voices = defaultdict(list)
    for line in lines[2:]:
        parts = line.split()
        if len(parts) < 2: continue
        name = parts[0]
        try:
            locale_parts = name.split('-')
            locale = f"{locale_parts[0]}-{locale_parts[1]}"
            voice_data = {"name": name, "gender": parts[1], "locale": locale, "short_name": '-'.join(locale_parts[2:])}
            ALL_VOICES.append(voice_data)
            locales_with_voices[locale].append(voice_data)
        except IndexError: logger.warning(f"Could not parse voice line: {line}")
    
    sorted_locales = sorted(locales_with_voices.keys(), key=lambda x: (x not in ['zh-CN', 'en-US'], locale_display_names.get(x, x)))
    for locale in sorted_locales:
        display_name = locale_display_names.get(locale, locale)
        SUPPORTED_LOCALES[locale] = display_name

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
def pre_process_text(text, options):
    logger.info(f"Applying text cleaning with options: {options}")
    processed_text = text
    if options.get('remove_markdown'):
        processed_text = re.sub(r'\[!\[([^\]]*)\]\([^\)]+\)\]\([^\)]+\)', r'\1', processed_text)
        processed_text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', processed_text)
        processed_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', processed_text)
        processed_text = re.sub(r'```[\s\S]*?```', '', processed_text)
        processed_text = re.sub(r'`([^`]+)`', r'\1', processed_text)
        processed_text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', processed_text)
        processed_text = re.sub(r'(\*|_)(.*?)\1', r'\2', processed_text)
        processed_text = re.sub(r'^\s*#+\s*', '', processed_text, flags=re.MULTILINE)
        processed_text = re.sub(r'^\s*[\*\-]\s*|\s*\d+\.\s*', '', processed_text, flags=re.MULTILINE)
        processed_text = re.sub(r'^\s*>\s?', '', processed_text, flags=re.MULTILINE)
        processed_text = re.sub(r'^\s*[-*_]{3,}\s*$', '', processed_text, flags=re.MULTILINE)
    if options.get('remove_emoji'):
        processed_text = emoji.replace_emoji(processed_text, replace='')
    if options.get('no_urls'):
        processed_text = re.sub(r'http\S+|www\S+|https\S+', '', processed_text, flags=re.MULTILINE)
    custom_keywords_str = options.get('custom_keywords', '')
    if custom_keywords_str:
        keywords = [re.escape(k.strip()) for k in custom_keywords_str.split(',') if k.strip()]
        if keywords:
            regex_pattern = '|'.join(keywords)
            processed_text = re.sub(regex_pattern, '', processed_text)
    if not options.get('no_line_breaks'):
        lines = processed_text.split('\n')
        reunited_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line: continue
            if reunited_lines and not reunited_lines[-1].strip().endswith(('。', '？', '！', '?', '!')):
                reunited_lines[-1] += ' ' + line
            else:
                reunited_lines.append(line)
        processed_text = '\n'.join(reunited_lines)
    else:
        processed_text = processed_text.replace('\n', ' ')
    processed_text = processed_text.replace('\t', ' ')
    # Remove spaces inserted between Chinese characters due to PDF line breaks
    processed_text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', processed_text)
    # Remove spaces around common Chinese punctuation
    processed_text = re.sub(r'\s+([，。、？！；：])', r'\1', processed_text)
    processed_text = re.sub(r'([，。、？！；：])\s+', r'\1', processed_text)
    processed_text = re.sub(r'([（《「『])\s+', r'\1', processed_text)
    processed_text = re.sub(r'\s+([）》」』])', r'\1', processed_text)
    processed_text = re.sub(r' +', ' ', processed_text)
    return processed_text.strip()

def split_text_intelligently(text, options, target_size=800, max_size=1500):
    processed_text = pre_process_text(text, options)
    sentences = re.split(r'((?<![0-9\uff10-\uff19])\.(?![0-9\uff10-\uff19])|[？！?!\n])', processed_text)
    rough_chunks = []
    for i in range(0, len(sentences) - 1, 2):
        chunk = sentences[i] + (sentences[i+1] if sentences[i+1] else '')
        if chunk.strip(): rough_chunks.append(chunk.strip())
    if len(sentences) % 2 != 0 and sentences[-1].strip():
        rough_chunks.append(sentences[-1].strip())
    if not rough_chunks: return [processed_text] if processed_text.strip() else []
    final_chunks = []
    current_chunk = ""
    for chunk in rough_chunks:
        is_paragraph_break = '\n' in chunk
        chunk_to_add = chunk.replace('\n', ' ').strip()
        if not chunk_to_add: continue
        if current_chunk and (len(current_chunk) + len(chunk_to_add) > max_size or (is_paragraph_break and len(current_chunk) > target_size)):
            final_chunks.append(current_chunk)
            current_chunk = chunk_to_add
        else:
            current_chunk = (current_chunk + " " + chunk_to_add) if current_chunk else chunk_to_add
    if current_chunk:
        final_chunks.append(current_chunk)
    logger.info(f"Intelligently split text into {len(final_chunks)} high-quality chunks.")
    return final_chunks

# 新的文本分块函数，优先按标点断句，并确保每块不超过 max_chunk_len
def split_text_into_chunks(text, max_chunk_len=300):
    sentences = re.split(r'(?<=[。！？!?.])(?!(\d)|$)', text)
    sentences = [s.strip() for s in sentences if isinstance(s, str) and s.strip()]

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_len:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(sentence) > max_chunk_len:
                sub_chunks = [sentence[i:i+max_chunk_len] for i in range(0, len(sentence), max_chunk_len)]
                chunks.extend(sub_chunks)
                current_chunk = ""
            else:
                current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

async def text_to_speech_with_retry(semaphore, chunk_index, text_chunk, voice, temp_dir):
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
                communicate = edge_tts.Communicate(text_chunk, voice)
                temp_file_path = os.path.join(temp_dir, f"segment_{chunk_index}.mp3")
                with open(temp_file_path, "wb") as temp_file:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            temp_file.write(chunk["data"])
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
):
    limit = max_concurrent_requests or MAX_CONCURRENT_REQUESTS
    logger.info(
        f"[Step 2/4] Starting TTS generation with concurrency limit: {limit}..."
    )
    semaphore = asyncio.Semaphore(limit)
    start_time = time.time()
    tasks = [text_to_speech_with_retry(semaphore, i, chunk, voice, temp_dir) for i, chunk in enumerate(text_chunks)]
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
def get_all_voices(): return jsonify(ALL_VOICES)

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
        MAX_CONCURRENT_REQUESTS = config.get("max_concurrent_requests", 20)
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

@app.route('/v1/audio/speech', methods=['POST'])
@token_required
async def generate_speech():
    request_start_time = time.time()
    logger.info("="*50)
    logger.info("Received new TTS request.")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            data = request.get_json()
            text, voice_name = data.get("input"), data.get("voice")
            stream_enabled = bool(data.get("stream", False))
            
            # 核心逻辑：决定使用哪套过滤规则
            if config.get('sync_api_filtering', False):
                cleaning_options = config.get('default_cleaning_options', {})
                logger.info("API filtering sync is ON. Using default cleaning options from config.")
            else:
                cleaning_options = data.get("cleaning_options", {})
                logger.info("API filtering sync is OFF. Using cleaning options from request body (if any).")
            
            if not text or not voice_name: return jsonify({"error": {"message": "Parameters 'input' and 'voice' are required"}}), 400

            final_voice = config['openai_voice_map'].get(voice_name, voice_name)
            logger.info("[Step 1/4] Pre-processing text...")
            processed_text = pre_process_text(text, cleaning_options)
            if processed_text is None:
                logger.error("\u274c processed_text is None!\uFF01\u8BF7\u68C0\u67E5\u524D\u9762\u7684\u6E05\u6D17\u903B\u8F91")

            # Override settings per request if provided
            chunk_size_override = (
                data.get("chunk_size")
                or request.args.get("chunk_size")
                or request.args.get("max_chunk_len")
                or CHUNK_SIZE
            )
            try:
                chunk_size_override = int(chunk_size_override)
            except (TypeError, ValueError):
                chunk_size_override = CHUNK_SIZE

            sync_chunks = data.get("sync_chunks") or request.args.get("sync_chunks", SYNC_CHUNKS)
            try:
                sync_chunks = int(sync_chunks)
            except (TypeError, ValueError):
                sync_chunks = SYNC_CHUNKS

            max_concurrent_requests_override = (
                data.get("max_concurrent_requests")
                or request.args.get("max_concurrent_requests")
                or MAX_CONCURRENT_REQUESTS
            )
            try:
                max_concurrent_requests_override = int(max_concurrent_requests_override)
            except (TypeError, ValueError):
                max_concurrent_requests_override = MAX_CONCURRENT_REQUESTS

            max_chunk_len = chunk_size_override

            text_chunks = split_text_into_chunks(processed_text, max_chunk_len=max_chunk_len)
            if not text_chunks:
                return jsonify({"error": {"message": "Input text is empty."}}), 400

            for idx, chunk in enumerate(text_chunks, 1):
                logger.info(f"Chunk {idx} length: {len(chunk)}")

            if stream_enabled:
                logger.info("Streaming mode enabled. Sending chunks as they are generated...")

                return Response(
                    generate_streaming_audio_sync(
                        text_chunks,
                        final_voice,
                        sync_chunks,
                        max_concurrent_requests_override,
                    ),
                    content_type="audio/mpeg",
                )

            temp_file_paths = await run_tts(
                text_chunks,
                final_voice,
                temp_dir,
                max_concurrent_requests_override,
            )
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
            
            return send_file(final_audio_stream, mimetype='audio/mpeg', as_attachment=False)
        except Exception as e:
            logger.error(f"An unexpected error occurred in generate_speech: {e}", exc_info=True)
            return jsonify({"error": {"message": "Internal server error."}}), 500

# --- 应用启动 ---
if __name__ == '__main__':
    initialize_config()
    parse_voices()
    
    port = int(config.get('port', 5050))
    logger.info(f"Server starting on http://0.0.0.0:{port}")
    if os.environ.get('WEBUI_PASSWORD'):
        logger.info("✅ WebUI password protection is enabled.")
    else:
        logger.warning("⚠️ WebUI is open to public access. Set WEBUI_PASSWORD in .env to enable protection.")
    if config.get('api_token'):
        logger.info(f"API Token is configured. Use 'Authorization: Bearer <Your-Token>' for API calls.")
    else:
        logger.warning("API Token is not configured. The API for TTS is open to public access.")
        
    app.run(host='0.0.0.0', port=port, debug=True)