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

import edge_tts
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# --- 配置和初始化 ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- 配置文件路径与全局变量 ---
CONFIG_FILE = 'config.json'
VOICES_LIST_FILE = os.path.join('tts_data', 'voices_list.txt')
LOCALES_MAP_FILE = os.path.join('tts_data', 'locales_map.json')
config = {}
ALL_VOICES = []
SUPPORTED_LOCALES = {}
MAX_CONCURRENT_REQUESTS = 20

# --- 数据加载与管理 ---
def load_config_from_file():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_config_to_file(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def initialize_config():
    global config
    loaded_config = load_config_from_file()
    if loaded_config is None:
        logger.info(f"'{CONFIG_FILE}' not found or invalid, creating a default one.")
        default_config = {
            "port": 5050,
            "api_token": "",
            "openai_voice_map": {
                "shimmer": "zh-CN-XiaoxiaoNeural",
                "alloy": "en-US-AriaNeural",
                "fable": "zh-CN-shaanxi-XiaoniNeural",
                "onyx": "en-US-ChristopherNeural",
                "nova": "en-US-AvaNeural",
                "echo": "zh-CN-YunyangNeural"
            }
        }
        save_config_to_file(default_config)
        config = default_config
    else:
        config = loaded_config

def parse_voices():
    global ALL_VOICES, SUPPORTED_LOCALES
    try:
        with open(VOICES_LIST_FILE, 'r', encoding='utf-8') as f:
            voices_raw_data = f.read()
        with open(LOCALES_MAP_FILE, 'r', encoding='utf-8') as f:
            locale_display_names = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}. Please ensure '{VOICES_LIST_FILE}' and '{LOCALES_MAP_FILE}' exist.")
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
        except IndexError:
            logger.warning(f"Could not parse voice line: {line}")
    
    sorted_locales = sorted(locales_with_voices.keys(), key=lambda x: (x not in ['zh-CN', 'en-US'], locale_display_names.get(x, x)))
    for locale in sorted_locales:
        display_name = locale_display_names.get(locale, locale)
        SUPPORTED_LOCALES[locale] = display_name

# --- Token 认证装饰器 ---
def token_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        api_token = config.get('api_token')
        if api_token:
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({"error": {"message": "Authorization header is missing or invalid."}}), 401
            
            provided_token = auth_header.split(' ')[1]
            if provided_token != api_token:
                return jsonify({"error": {"message": "Invalid API token."}}), 403
            
        return await f(*args, **kwargs)
    return decorated_function

# --- 核心业务逻辑 (V9: 精炼后的高级文本处理) ---
def pre_process_text(text):
    """高级文本净化与重组"""
    # 替换各种不可见字符和多余的空白
    text = text.replace('\t', ' ').replace('\r', '')
    text = re.sub(r' +', ' ', text)
    
    # 智能合并被错误切断的行
    lines = text.split('\n')
    reunited_lines = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
        
        # 如果上一行存在，且不以强标点结尾，则认为当前换行是无意义的格式化换行，进行合并
        if reunited_lines and not reunited_lines[-1].strip().endswith(('。', '？', '！', '?', '!')):
            reunited_lines[-1] += ' ' + line
        else:
            reunited_lines.append(line)
            
    # 将处理过的行重新组合成一个文本块，用一个特殊的标记代表有意义的段落分隔
    return '<PARA_BREAK>'.join(reunited_lines)

def split_text_intelligently(text, target_size=800, max_size=1500):
    """最终的智能分块算法"""
    processed_text = pre_process_text(text)
    
    # 使用带零宽断言的正则表达式，避免错误切分数字，同时将段落标记也作为强分隔符
    sentences = re.split(r'((?<![0-9\uff10-\uff19])\.(?![0-9\uff10-\uff19])|[？！?!]|<PARA_BREAK>)', processed_text)
    
    rough_chunks = []
    for i in range(0, len(sentences) - 1, 2):
        chunk = sentences[i] + (sentences[i+1] if sentences[i+1] else '')
        if chunk.strip():
            rough_chunks.append(chunk.strip())
    if len(sentences) % 2 != 0 and sentences[-1].strip():
        rough_chunks.append(sentences[-1].strip())
        
    if not rough_chunks:
        return [processed_text] if processed_text.strip() else []

    # 智能合并逻辑
    final_chunks = []
    current_chunk = ""
    for chunk in rough_chunks:
        # 如果遇到段落标记，则强制结束当前块
        is_paragraph_break = '<PARA_BREAK>' in chunk
        chunk_to_add = chunk.replace('<PARA_BREAK>', ' ').strip()
        
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

async def text_to_speech_with_retry(semaphore, chunk_index, text_chunk, voice, temp_dir):
    async with semaphore:
        task_start_time = time.time()
        max_retries = 10
        logger.info(f"  [Task {chunk_index+1}] Starting processing for chunk: '{text_chunk[:30]}...'")
        
        for attempt in range(max_retries):
            try:
                communicate = edge_tts.Communicate(text_chunk, voice)
                temp_file_path = os.path.join(temp_dir, f"segment_{chunk_index}.mp3")
                with open(temp_file_path, "wb") as temp_file:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            temp_file.write(chunk["data"])
                
                if os.path.getsize(temp_file_path) > 0:
                    elapsed_time = time.time() - task_start_time
                    logger.info(f"  [Task {chunk_index+1}] Successfully generated in {elapsed_time:.2f}s.")
                    return temp_file_path
                else:
                    raise edge_tts.NoAudioReceived("No audio was received (empty file).")
                    
            except Exception as e:
                logger.warning(f"  [Task {chunk_index+1}] Attempt {attempt + 1}/{max_retries} failed. Error: {e}")
                if attempt + 1 == max_retries:
                    logger.error(f"  [Task {chunk_index+1}] Failed after {max_retries} attempts. Giving up.")
                    return None
                
                wait_time = min(2 ** attempt, 8)
                logger.info(f"  [Task {chunk_index+1}] Retrying in {wait_time} second(s)...")
                await asyncio.sleep(wait_time)

# --- Flask 路由和 API ---
@app.route('/')
def index():
    return render_template('index.html', locales=SUPPORTED_LOCALES)

@app.route('/v1/audio/all_voices', methods=['GET'])
def get_all_voices():
    return jsonify(ALL_VOICES)

@app.route('/v1/config', methods=['GET'])
def get_config():
    return jsonify(config)

@app.route('/v1/config', methods=['POST'])
def update_config():
    global config
    try:
        new_data = request.get_json()
        if not all(k in new_data for k in ['port', 'api_token', 'openai_voice_map']):
            return jsonify({"error": "Invalid data format"}), 400
        config.update(new_data)
        save_config_to_file(config)
        logger.info("Configuration updated and saved successfully.")
        return jsonify({"message": "设置已保存。音色映射和API Token立即生效，端口修改需重启服务才能应用。"})
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
            if not text or not voice_name:
                return jsonify({"error": {"message": "Parameters 'input' and 'voice' are required"}}), 400

            final_voice = config['openai_voice_map'].get(voice_name, voice_name)
            
            logger.info("[Step 1/4] Pre-processing and splitting text into chunks...")
            text_chunks = split_text_intelligently(text)
            if not text_chunks:
                return jsonify({"error": {"message": "Input text is empty."}}), 400

            logger.info(f"[Step 2/4] Starting TTS generation with concurrency limit: {MAX_CONCURRENT_REQUESTS}...")
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            tasks = [text_to_speech_with_retry(semaphore, i, chunk, final_voice, temp_dir) for i, chunk in enumerate(text_chunks)]
            temp_file_paths = await asyncio.gather(*tasks)
            generation_duration = time.time() - request_start_time
            logger.info(f"Concurrent generation finished in {generation_duration:.2f}s.")
            
            logger.info("[Step 3/4] Stitching audio segments using FFmpeg...")
            stitching_start_time = time.time()
            
            list_file_path = os.path.join(temp_dir, "file_list.txt")
            failed_chunks_indices = []
            with open(list_file_path, "w", encoding='utf-8') as f:
                for i, path in enumerate(temp_file_paths):
                    if path:
                        f.write(f"file '{os.path.basename(path)}'\n")
                    else:
                        silent_path = os.path.join(temp_dir, f"silent_{i}.mp3")
                        subprocess.run(
                            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.2", "-q:a", "9", silent_path],
                            check=True, capture_output=True
                        )
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
            with open(output_file_path, 'rb') as f:
                final_audio_data = f.read()
            final_audio_stream = BytesIO(final_audio_data)

            total_request_duration = time.time() - request_start_time
            logger.info("="*50)
            logger.info("TTS Request Summary:")
            logger.info(f"  - Total Chunks: {len(text_chunks)}")
            logger.info(f"  - Successful Chunks: {len(text_chunks) - len(failed_chunks_indices)}")
            logger.info(f"  - Failed Chunks: {len(failed_chunks_indices)}")
            if failed_chunks_indices:
                logger.warning(f"  - Indices of Failed Chunks: {failed_chunks_indices}")
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
    if config.get('api_token'):
        logger.info(f"API Token is configured. Use 'Authorization: Bearer <Your-Token>' for API calls.")
    else:
        logger.warning("API Token is not configured. The API is open to public access.")
    app.run(host='0.0.0.0', port=port, debug=True)