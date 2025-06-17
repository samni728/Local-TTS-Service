import os
import asyncio
import logging
import json
import re
from io import BytesIO
from collections import defaultdict

import edge_tts
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from pydub import AudioSegment

# --- 配置和初始化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- 配置文件路径 ---
CONFIG_FILE = 'config.json'
VOICES_LIST_FILE = os.path.join('tts_data', 'voices_list.txt')
LOCALES_MAP_FILE = os.path.join('tts_data', 'locales_map.json')

# --- 全局变量 ---
config = {}
ALL_VOICES = []
SUPPORTED_LOCALES = {}

# --- 数据加载与管理 ---
def load_config_from_file():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return None

def save_config_to_file(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def initialize_config():
    global config
    loaded_config = load_config_from_file()
    if loaded_config is None:
        logger.info(f"'{CONFIG_FILE}' not found, creating a default one.")
        default_config = {
            "port": 5050,
            "openai_voice_map": {
                "shimmer": "zh-CN-XiaoxiaoNeural", "alloy": "en-US-AriaNeural",
                "fable": "zh-CN-shaanxi-XiaoniNeural", "onyx": "en-US-ChristopherNeural",
                "nova": "en-US-AvaNeural", "echo": "zh-CN-YunyangNeural"
            }
        }
        save_config_to_file(default_config)
        config = default_config
    else: config = loaded_config

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

# --- 核心业务逻辑 ---
def split_text(text):
    text = text.replace('\r', ' ').replace('\n', ' ')
    sentences = re.split(r'([.。？！?!])', text)
    chunks = []
    for i in range(0, len(sentences) - 1, 2):
        chunk = sentences[i] + (sentences[i+1] if sentences[i+1] else '')
        if chunk.strip(): chunks.append(chunk.strip())
    if len(sentences) % 2 != 0 and sentences[-1].strip():
        chunks.append(sentences[-1].strip())
    if not chunks: chunks = [text] if text.strip() else []
    logger.info(f"Text split into {len(chunks)} chunks.")
    return chunks

async def text_to_speech_task(text_chunk, voice):
    try:
        communicate = edge_tts.Communicate(text_chunk, voice)
        audio_stream = BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_stream.write(chunk["data"])
        audio_stream.seek(0)
        return audio_stream
    except Exception as e:
        logger.error(f"TTS task failed for chunk '{text_chunk[:20]}...': {e}")
        return None

# --- Flask 路由和 API ---
@app.route('/')
def index():
    return render_template('index.html', locales=SUPPORTED_LOCALES)

@app.route('/v1/audio/all_voices', methods=['GET'])
def get_all_voices(): return jsonify(ALL_VOICES)

@app.route('/v1/config', methods=['GET'])
def get_config(): return jsonify(config)

@app.route('/v1/config', methods=['POST'])
def update_config():
    global config
    try:
        new_data = request.get_json()
        if not isinstance(new_data.get('port'), int) or not isinstance(new_data.get('openai_voice_map'), dict):
            return jsonify({"error": "Invalid data format"}), 400
        
        config['openai_voice_map'] = new_data['openai_voice_map']
        full_config_to_save = config.copy()
        full_config_to_save['port'] = new_data['port']
        save_config_to_file(full_config_to_save)
        
        logger.info("Configuration updated and saved successfully.")
        return jsonify({"message": "设置已保存。音色映射立即生效，端口修改需重启服务才能应用。"})
    except Exception as e:
        logger.error(f"Error updating config: {e}", exc_info=True)
        return jsonify({"error": "更新配置时发生内部错误。"}), 500

@app.route('/v1/audio/speech', methods=['POST'])
async def generate_speech():
    try:
        data = request.get_json()
        text, voice_name = data.get("input"), data.get("voice")
        if not text or not voice_name:
            return jsonify({"error": {"message": "Parameters 'input' and 'voice' are required"}}), 400

        final_voice = config['openai_voice_map'].get(voice_name, voice_name)
        text_chunks = split_text(text)
        if not text_chunks: return jsonify({"error": {"message": "Input text is empty."}}), 400

        logger.info(f"Starting concurrent TTS generation for {len(text_chunks)} chunks...")
        tasks = [text_to_speech_task(chunk, final_voice) for chunk in text_chunks]
        audio_segments_streams = await asyncio.gather(*tasks)

        final_audio = AudioSegment.empty()
        for audio_stream in audio_segments_streams:
            if audio_stream and audio_stream.getbuffer().nbytes > 0:
                segment = AudioSegment.from_mp3(audio_stream)
                final_audio += segment
            else: final_audio += AudioSegment.silent(duration=200)

        if len(final_audio) == 0:
            logger.error("Final audio is empty. All TTS tasks may have failed.")
            return jsonify({"error": {"message": "Failed to generate any audio."}}), 500

        final_audio_stream = BytesIO()
        final_audio.export(final_audio_stream, format="mp3")
        final_audio_stream.seek(0)

        logger.info(f"Successfully stitched audio. Final duration: {len(final_audio) / 1000.0}s")
        return send_file(final_audio_stream, mimetype='audio/mpeg', as_attachment=False)
    except Exception as e:
        logger.error(f"An error occurred in generate_speech: {e}", exc_info=True)
        return jsonify({"error": {"message": "Internal server error."}}), 500

# --- 应用启动 ---
if __name__ == '__main__':
    initialize_config()
    parse_voices()
    port = int(config.get('port', 5050))
    logger.info(f"Server starting on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)