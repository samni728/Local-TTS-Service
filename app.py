import os
import asyncio
import logging
import json
from io import BytesIO
from collections import defaultdict

import edge_tts
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# --- 配置和初始化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- 配置文件管理 ---
CONFIG_FILE = 'config.json'
config = {}

def load_config_from_file():
    """从文件加载配置，如果失败则返回 None"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_config_to_file(data):
    """保存配置到文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def initialize_config():
    """初始化全局配置变量"""
    global config
    loaded_config = load_config_from_file()
    if loaded_config is None:
        logger.info(f"'{CONFIG_FILE}' not found or invalid, creating a default one.")
        default_config = {
            "port": 5000,
            "openai_voice_map": {
                "shimmer": "zh-CN-XiaoxiaoNeural", "alloy": "en-US-AriaNeural",
                "fable": "zh-CN-shaanxi-XiaoniNeural", "onyx": "en-US-ChristopherNeural",
                "nova": "en-US-AvaNeural", "echo": "zh-CN-YunyangNeural"
            }
        }
        save_config_to_file(default_config)
        config = default_config
    else:
        config = loaded_config

# --- 全局语音数据 ---
ALL_VOICES = []
SUPPORTED_LOCALES = {}

def parse_voices():
    global ALL_VOICES, SUPPORTED_LOCALES
    
    voices_raw_data = """
Name                               Gender    ContentCategories      VoicePersonalities
---------------------------------  --------  ---------------------  --------------------------------------
af-ZA-AdriNeural                   Female    General                Friendly, Positive
af-ZA-WillemNeural                 Male      General                Friendly, Positive
am-ET-AmehaNeural                  Male      General                Friendly, Positive
am-ET-MekdesNeural                 Female    General                Friendly, Positive
ar-AE-FatimaNeural                 Female    General                Friendly, Positive
ar-AE-HamdanNeural                 Male      General                Friendly, Positive
ar-BH-AliNeural                    Male      General                Friendly, Positive
ar-BH-LailaNeural                  Female    General                Friendly, Positive
ar-DZ-AminaNeural                  Female    General                Friendly, Positive
ar-DZ-IsmaelNeural                 Male      General                Friendly, Positive
ar-EG-SalmaNeural                  Female    General                Friendly, Positive
ar-EG-ShakirNeural                 Male      General                Friendly, Positive
ar-IQ-BasselNeural                 Male      General                Friendly, Positive
ar-IQ-RanaNeural                   Female    General                Friendly, Positive
ar-JO-SanaNeural                   Female    General                Friendly, Positive
ar-JO-TaimNeural                   Male      General                Friendly, Positive
ar-KW-FahedNeural                  Male      General                Friendly, Positive
ar-KW-NouraNeural                  Female    General                Friendly, Positive
ar-LB-LaylaNeural                  Female    General                Friendly, Positive
ar-LB-RamiNeural                   Male      General                Friendly, Positive
ar-LY-ImanNeural                   Female    General                Friendly, Positive
ar-LY-OmarNeural                   Male      General                Friendly, Positive
ar-MA-JamalNeural                  Male      General                Friendly, Positive
ar-MA-MounaNeural                  Female    General                Friendly, Positive
ar-OM-AbdullahNeural               Male      General                Friendly, Positive
ar-OM-AyshaNeural                  Female    General                Friendly, Positive
ar-QA-AmalNeural                   Female    General                Friendly, Positive
ar-QA-MoazNeural                   Male      General                Friendly, Positive
ar-SA-HamedNeural                  Male      General                Friendly, Positive
ar-SA-ZariyahNeural                Female    General                Friendly, Positive
ar-SY-AmanyNeural                  Female    General                Friendly, Positive
ar-SY-LaithNeural                  Male      General                Friendly, Positive
ar-TN-HediNeural                   Male      General                Friendly, Positive
ar-TN-ReemNeural                   Female    General                Friendly, Positive
ar-YE-MaryamNeural                 Female    General                Friendly, Positive
ar-YE-SalehNeural                  Male      General                Friendly, Positive
az-AZ-BabekNeural                  Male      General                Friendly, Positive
az-AZ-BanuNeural                   Female    General                Friendly, Positive
bg-BG-BorislavNeural               Male      General                Friendly, Positive
bg-BG-KalinaNeural                 Female    General                Friendly, Positive
bn-BD-NabanitaNeural               Female    General                Friendly, Positive
bn-BD-PradeepNeural                Male      General                Friendly, Positive
bn-IN-BashkarNeural                Male      General                Friendly, Positive
bn-IN-TanishaaNeural               Female    General                Friendly, Positive
bs-BA-GoranNeural                  Male      General                Friendly, Positive
bs-BA-VesnaNeural                  Female    General                Friendly, Positive
ca-ES-EnricNeural                  Male      General                Friendly, Positive
ca-ES-JoanaNeural                  Female    General                Friendly, Positive
cs-CZ-AntoninNeural                Male      General                Friendly, Positive
cs-CZ-VlastaNeural                 Female    General                Friendly, Positive
cy-GB-AledNeural                   Male      General                Friendly, Positive
cy-GB-NiaNeural                    Female    General                Friendly, Positive
da-DK-ChristelNeural               Female    General                Friendly, Positive
da-DK-JeppeNeural                  Male      General                Friendly, Positive
de-AT-IngridNeural                 Female    General                Friendly, Positive
de-AT-JonasNeural                  Male      General                Friendly, Positive
de-CH-JanNeural                    Male      General                Friendly, Positive
de-CH-LeniNeural                   Female    General                Friendly, Positive
de-DE-AmalaNeural                  Female    General                Friendly, Positive
de-DE-ConradNeural                 Male      General                Friendly, Positive
de-DE-FlorianMultilingualNeural    Male      General                Friendly, Positive
de-DE-KatjaNeural                  Female    General                Friendly, Positive
de-DE-KillianNeural                Male      General                Friendly, Positive
de-DE-SeraphinaMultilingualNeural  Female    General                Friendly, Positive
el-GR-AthinaNeural                 Female    General                Friendly, Positive
el-GR-NestorasNeural               Male      General                Friendly, Positive
en-AU-NatashaNeural                Female    General                Friendly, Positive
en-AU-WilliamNeural                Male      General                Friendly, Positive
en-CA-ClaraNeural                  Female    General                Friendly, Positive
en-CA-LiamNeural                   Male      General                Friendly, Positive
en-GB-LibbyNeural                  Female    General                Friendly, Positive
en-GB-MaisieNeural                 Female    General                Friendly, Positive
en-GB-RyanNeural                   Male      General                Friendly, Positive
en-GB-SoniaNeural                  Female    General                Friendly, Positive
en-GB-ThomasNeural                 Male      General                Friendly, Positive
en-HK-SamNeural                    Male      General                Friendly, Positive
en-HK-YanNeural                    Female    General                Friendly, Positive
en-IE-ConnorNeural                 Male      General                Friendly, Positive
en-IE-EmilyNeural                  Female    General                Friendly, Positive
en-IN-NeerjaExpressiveNeural       Female    General                Friendly, Positive
en-IN-NeerjaNeural                 Female    General                Friendly, Positive
en-IN-PrabhatNeural                Male      General                Friendly, Positive
en-KE-AsiliaNeural                 Female    General                Friendly, Positive
en-KE-ChilembaNeural               Male      General                Friendly, Positive
en-NG-AbeoNeural                   Male      General                Friendly, Positive
en-NG-EzinneNeural                 Female    General                Friendly, Positive
en-NZ-MitchellNeural               Male      General                Friendly, Positive
en-NZ-MollyNeural                  Female    General                Friendly, Positive
en-PH-JamesNeural                  Male      General                Friendly, Positive
en-PH-RosaNeural                   Female    General                Friendly, Positive
en-SG-LunaNeural                   Female    General                Friendly, Positive
en-SG-WayneNeural                  Male      General                Friendly, Positive
en-TZ-ElimuNeural                  Male      General                Friendly, Positive
en-TZ-ImaniNeural                  Female    General                Friendly, Positive
en-US-AnaNeural                    Female    Cartoon, Conversation  Cute
en-US-AndrewMultilingualNeural     Male      Conversation, Copilot  Warm, Confident, Authentic, Honest
en-US-AndrewNeural                 Male      Conversation, Copilot  Warm, Confident, Authentic, Honest
en-US-AriaNeural                   Female    News, Novel            Positive, Confident
en-US-AvaMultilingualNeural        Female    Conversation, Copilot  Expressive, Caring, Pleasant, Friendly
en-US-AvaNeural                    Female    Conversation, Copilot  Expressive, Caring, Pleasant, Friendly
en-US-BrianMultilingualNeural      Male      Conversation, Copilot  Approachable, Casual, Sincere
en-US-BrianNeural                  Male      Conversation, Copilot  Approachable, Casual, Sincere
en-US-ChristopherNeural            Male      News, Novel            Reliable, Authority
en-US-EmmaMultilingualNeural       Female    Conversation, Copilot  Cheerful, Clear, Conversational
en-US-EmmaNeural                   Female    Conversation, Copilot  Cheerful, Clear, Conversational
en-US-EricNeural                   Male      News, Novel            Rational
en-US-GuyNeural                    Male      News, Novel            Passion
en-US-JennyNeural                  Female    General                Friendly, Considerate, Comfort
en-US-MichelleNeural               Female    News, Novel            Friendly, Pleasant
en-US-RogerNeural                  Male      News, Novel            Lively
en-US-SteffanNeural                Male      News, Novel            Rational
en-ZA-LeahNeural                   Female    General                Friendly, Positive
en-ZA-LukeNeural                   Male      General                Friendly, Positive
es-AR-ElenaNeural                  Female    General                Friendly, Positive
es-AR-TomasNeural                  Male      General                Friendly, Positive
es-BO-MarceloNeural                Male      General                Friendly, Positive
es-BO-SofiaNeural                  Female    General                Friendly, Positive
es-CL-CatalinaNeural               Female    General                Friendly, Positive
es-CL-LorenzoNeural                Male      General                Friendly, Positive
es-CO-GonzaloNeural                Male      General                Friendly, Positive
es-CO-SalomeNeural                 Female    General                Friendly, Positive
es-CR-JuanNeural                   Male      General                Friendly, Positive
es-CR-MariaNeural                  Female    General                Friendly, Positive
es-CU-BelkysNeural                 Female    General                Friendly, Positive
es-CU-ManuelNeural                 Male      General                Friendly, Positive
es-DO-EmilioNeural                 Male      General                Friendly, Positive
es-DO-RamonaNeural                 Female    General                Friendly, Positive
es-EC-AndreaNeural                 Female    General                Friendly, Positive
es-EC-LuisNeural                   Male      General                Friendly, Positive
es-ES-AlvaroNeural                 Male      General                Friendly, Positive
es-ES-ElviraNeural                 Female    General                Friendly, Positive
es-ES-XimenaNeural                 Female    General                Friendly, Positive
es-GQ-JavierNeural                 Male      General                Friendly, Positive
es-GQ-TeresaNeural                 Female    General                Friendly, Positive
es-GT-AndresNeural                 Male      General                Friendly, Positive
es-GT-MartaNeural                  Female    General                Friendly, Positive
es-HN-CarlosNeural                 Male      General                Friendly, Positive
es-HN-KarlaNeural                  Female    General                Friendly, Positive
es-MX-DaliaNeural                  Female    General                Friendly, Positive
es-MX-JorgeNeural                  Male      General                Friendly, Positive
es-NI-FedericoNeural               Male      General                Friendly, Positive
es-NI-YolandaNeural                Female    General                Friendly, Positive
es-PA-MargaritaNeural              Female    General                Friendly, Positive
es-PA-RobertoNeural                Male      General                Friendly, Positive
es-PE-AlexNeural                   Male      General                Friendly, Positive
es-PE-CamilaNeural                 Female    General                Friendly, Positive
es-PR-KarinaNeural                 Female    General                Friendly, Positive
es-PR-VictorNeural                 Male      General                Friendly, Positive
es-PY-MarioNeural                  Male      General                Friendly, Positive
es-PY-TaniaNeural                  Female    General                Friendly, Positive
es-SV-LorenaNeural                 Female    General                Friendly, Positive
es-SV-RodrigoNeural                Male      General                Friendly, Positive
es-US-AlonsoNeural                 Male      General                Friendly, Positive
es-US-PalomaNeural                 Female    General                Friendly, Positive
es-UY-MateoNeural                  Male      General                Friendly, Positive
es-UY-ValentinaNeural              Female    General                Friendly, Positive
es-VE-PaolaNeural                  Female    General                Friendly, Positive
es-VE-SebastianNeural              Male      General                Friendly, Positive
et-EE-AnuNeural                    Female    General                Friendly, Positive
et-EE-KertNeural                   Male      General                Friendly, Positive
fa-IR-DilaraNeural                 Female    General                Friendly, Positive
fa-IR-FaridNeural                  Male      General                Friendly, Positive
fi-FI-HarriNeural                  Male      General                Friendly, Positive
fi-FI-NooraNeural                  Female    General                Friendly, Positive
fil-PH-AngeloNeural                Male      General                Friendly, Positive
fil-PH-BlessicaNeural              Female    General                Friendly, Positive
fr-BE-CharlineNeural               Female    General                Friendly, Positive
fr-BE-GerardNeural                 Male      General                Friendly, Positive
fr-CA-AntoineNeural                Male      General                Friendly, Positive
fr-CA-JeanNeural                   Male      General                Friendly, Positive
fr-CA-SylvieNeural                 Female    General                Friendly, Positive
fr-CA-ThierryNeural                Male      General                Friendly, Positive
fr-CH-ArianeNeural                 Female    General                Friendly, Positive
fr-CH-FabriceNeural                Male      General                Friendly, Positive
fr-FR-DeniseNeural                 Female    General                Friendly, Positive
fr-FR-EloiseNeural                 Female    General                Friendly, Positive
fr-FR-HenriNeural                  Male      General                Friendly, Positive
fr-FR-RemyMultilingualNeural       Male      General                Friendly, Positive
fr-FR-VivienneMultilingualNeural   Female    General                Friendly, Positive
ga-IE-ColmNeural                   Male      General                Friendly, Positive
ga-IE-OrlaNeural                   Female    General                Friendly, Positive
gl-ES-RoiNeural                    Male      General                Friendly, Positive
gl-ES-SabelaNeural                 Female    General                Friendly, Positive
gu-IN-DhwaniNeural                 Female    General                Friendly, Positive
gu-IN-NiranjanNeural               Male      General                Friendly, Positive
he-IL-AvriNeural                   Male      General                Friendly, Positive
he-IL-HilaNeural                   Female    General                Friendly, Positive
hi-IN-MadhurNeural                 Male      General                Friendly, Positive
hi-IN-SwaraNeural                  Female    General                Friendly, Positive
hr-HR-GabrijelaNeural              Female    General                Friendly, Positive
hr-HR-SreckoNeural                 Male      General                Friendly, Positive
hu-HU-NoemiNeural                  Female    General                Friendly, Positive
hu-HU-TamasNeural                  Male      General                Friendly, Positive
id-ID-ArdiNeural                   Male      General                Friendly, Positive
id-ID-GadisNeural                  Female    General                Friendly, Positive
is-IS-GudrunNeural                 Female    General                Friendly, Positive
is-IS-GunnarNeural                 Male      General                Friendly, Positive
it-IT-DiegoNeural                  Male      General                Friendly, Positive
it-IT-ElsaNeural                   Female    General                Friendly, Positive
it-IT-GiuseppeMultilingualNeural   Male      General                Friendly, Positive
it-IT-IsabellaNeural               Female    General                Friendly, Positive
iu-Cans-CA-SiqiniqNeural           Female    General                Friendly, Positive
iu-Cans-CA-TaqqiqNeural            Male      General                Friendly, Positive
iu-Latn-CA-SiqiniqNeural           Female    General                Friendly, Positive
iu-Latn-CA-TaqqiqNeural            Male      General                Friendly, Positive
ja-JP-KeitaNeural                  Male      General                Friendly, Positive
ja-JP-NanamiNeural                 Female    General                Friendly, Positive
jv-ID-DimasNeural                  Male      General                Friendly, Positive
jv-ID-SitiNeural                   Female    General                Friendly, Positive
ka-GE-EkaNeural                    Female    General                Friendly, Positive
ka-GE-GiorgiNeural                 Male      General                Friendly, Positive
kk-KZ-AigulNeural                  Female    General                Friendly, Positive
kk-KZ-DauletNeural                 Male      General                Friendly, Positive
km-KH-PisethNeural                 Male      General                Friendly, Positive
km-KH-SreymomNeural                Female    General                Friendly, Positive
kn-IN-GaganNeural                  Male      General                Friendly, Positive
kn-IN-SapnaNeural                  Female    General                Friendly, Positive
ko-KR-HyunsuMultilingualNeural     Male      General                Friendly, Positive
ko-KR-InJoonNeural                 Male      General                Friendly, Positive
ko-KR-SunHiNeural                  Female    General                Friendly, Positive
lo-LA-ChanthavongNeural            Male      General                Friendly, Positive
lo-LA-KeomanyNeural                Female    General                Friendly, Positive
lt-LT-LeonasNeural                 Male      General                Friendly, Positive
lt-LT-OnaNeural                    Female    General                Friendly, Positive
lv-LV-EveritaNeural                Female    General                Friendly, Positive
lv-LV-NilsNeural                   Male      General                Friendly, Positive
mk-MK-AleksandarNeural             Male      General                Friendly, Positive
mk-MK-MarijaNeural                 Female    General                Friendly, Positive
ml-IN-MidhunNeural                 Male      General                Friendly, Positive
ml-IN-SobhanaNeural                Female    General                Friendly, Positive
mn-MN-BataaNeural                  Male      General                Friendly, Positive
mn-MN-YesuiNeural                  Female    General                Friendly, Positive
mr-IN-AarohiNeural                 Female    General                Friendly, Positive
mr-IN-ManoharNeural                Male      General                Friendly, Positive
ms-MY-OsmanNeural                  Male      General                Friendly, Positive
ms-MY-YasminNeural                 Female    General                Friendly, Positive
mt-MT-GraceNeural                  Female    General                Friendly, Positive
mt-MT-JosephNeural                 Male      General                Friendly, Positive
my-MM-NilarNeural                  Female    General                Friendly, Positive
my-MM-ThihaNeural                  Male      General                Friendly, Positive
nb-NO-FinnNeural                   Male      General                Friendly, Positive
nb-NO-PernilleNeural               Female    General                Friendly, Positive
ne-NP-HemkalaNeural                Female    General                Friendly, Positive
ne-NP-SagarNeural                  Male      General                Friendly, Positive
nl-BE-ArnaudNeural                 Male      General                Friendly, Positive
nl-BE-DenaNeural                   Female    General                Friendly, Positive
nl-NL-ColetteNeural                Female    General                Friendly, Positive
nl-NL-FennaNeural                  Female    General                Friendly, Positive
nl-NL-MaartenNeural                Male      General                Friendly, Positive
pl-PL-MarekNeural                  Male      General                Friendly, Positive
pl-PL-ZofiaNeural                  Female    General                Friendly, Positive
ps-AF-GulNawazNeural               Male      General                Friendly, Positive
ps-AF-LatifaNeural                 Female    General                Friendly, Positive
pt-BR-AntonioNeural                Male      General                Friendly, Positive
pt-BR-FranciscaNeural              Female    General                Friendly, Positive
pt-BR-ThalitaMultilingualNeural    Female    General                Friendly, Positive
pt-PT-DuarteNeural                 Male      General                Friendly, Positive
pt-PT-RaquelNeural                 Female    General                Friendly, Positive
ro-RO-AlinaNeural                  Female    General                Friendly, Positive
ro-RO-EmilNeural                   Male      General                Friendly, Positive
ru-RU-DmitryNeural                 Male      General                Friendly, Positive
ru-RU-SvetlanaNeural               Female    General                Friendly, Positive
si-LK-SameeraNeural                Male      General                Friendly, Positive
si-LK-ThiliniNeural                Female    General                Friendly, Positive
sk-SK-LukasNeural                  Male      General                Friendly, Positive
sk-SK-ViktoriaNeural               Female    General                Friendly, Positive
sl-SI-PetraNeural                  Female    General                Friendly, Positive
sl-SI-RokNeural                    Male      General                Friendly, Positive
so-SO-MuuseNeural                  Male      General                Friendly, Positive
so-SO-UbaxNeural                   Female    General                Friendly, Positive
sq-AL-AnilaNeural                  Female    General                Friendly, Positive
sq-AL-IlirNeural                   Male      General                Friendly, Positive
sr-RS-NicholasNeural               Male      General                Friendly, Positive
sr-RS-SophieNeural                 Female    General                Friendly, Positive
su-ID-JajangNeural                 Male      General                Friendly, Positive
su-ID-TutiNeural                   Female    General                Friendly, Positive
sv-SE-MattiasNeural                Male      General                Friendly, Positive
sv-SE-SofieNeural                  Female    General                Friendly, Positive
sw-KE-RafikiNeural                 Male      General                Friendly, Positive
sw-KE-ZuriNeural                   Female    General                Friendly, Positive
sw-TZ-DaudiNeural                  Male      General                Friendly, Positive
sw-TZ-RehemaNeural                 Female    General                Friendly, Positive
ta-IN-PallaviNeural                Female    General                Friendly, Positive
ta-IN-ValluvarNeural               Male      General                Friendly, Positive
ta-LK-KumarNeural                  Male      General                Friendly, Positive
ta-LK-SaranyaNeural                Female    General                Friendly, Positive
ta-MY-KaniNeural                   Female    General                Friendly, Positive
ta-MY-SuryaNeural                  Male      General                Friendly, Positive
ta-SG-AnbuNeural                   Male      General                Friendly, Positive
ta-SG-VenbaNeural                  Female    General                Friendly, Positive
te-IN-MohanNeural                  Male      General                Friendly, Positive
te-IN-ShrutiNeural                 Female    General                Friendly, Positive
th-TH-NiwatNeural                  Male      General                Friendly, Positive
th-TH-PremwadeeNeural              Female    General                Friendly, Positive
tr-TR-AhmetNeural                  Male      General                Friendly, Positive
tr-TR-EmelNeural                   Female    General                Friendly, Positive
uk-UA-OstapNeural                  Male      General                Friendly, Positive
uk-UA-PolinaNeural                 Female    General                Friendly, Positive
ur-IN-GulNeural                    Female    General                Friendly, Positive
ur-IN-SalmanNeural                 Male      General                Friendly, Positive
ur-PK-AsadNeural                   Male      General                Friendly, Positive
ur-PK-UzmaNeural                   Female    General                Friendly, Positive
uz-UZ-MadinaNeural                 Female    General                Friendly, Positive
uz-UZ-SardorNeural                 Male      General                Friendly, Positive
vi-VN-HoaiMyNeural                 Female    General                Friendly, Positive
vi-VN-NamMinhNeural                Male      General                Friendly, Positive
zh-CN-XiaoxiaoNeural               Female    News, Novel            Warm
zh-CN-XiaoyiNeural                 Female    Cartoon, Novel         Lively
zh-CN-YunjianNeural                Male      Sports, Novel          Passion
zh-CN-YunxiNeural                  Male      Novel                  Lively, Sunshine
zh-CN-YunxiaNeural                 Male      Cartoon, Novel         Cute
zh-CN-YunyangNeural                Male      News                   Professional, Reliable
zh-CN-liaoning-XiaobeiNeural       Female    Dialect                Humorous
zh-CN-shaanxi-XiaoniNeural         Female    Dialect                Bright
zh-HK-HiuGaaiNeural                Female    General                Friendly, Positive
zh-HK-HiuMaanNeural                Female    General                Friendly, Positive
zh-HK-WanLungNeural                Male      General                Friendly, Positive
zh-TW-HsiaoChenNeural              Female    General                Friendly, Positive
zh-TW-HsiaoYuNeural                Female    General                Friendly, Positive
zh-TW-YunJheNeural                 Male      General                Friendly, Positive
zu-ZA-ThandoNeural                 Female    General                Friendly, Positive
zu-ZA-ThembaNeural                 Male      General                Friendly, Positive
"""
    locale_display_names = {
        "af-ZA": "南非语 (南非)", "am-ET": "阿姆哈拉语 (埃塞俄比亚)", "ar-AE": "阿拉伯语 (阿联酋)", "ar-BH": "阿拉伯语 (巴林)",
        "ar-DZ": "阿拉伯语 (阿尔及利亚)", "ar-EG": "阿拉伯语 (埃及)", "ar-IQ": "阿拉伯语 (伊拉克)", "ar-JO": "阿拉伯语 (约旦)",
        "ar-KW": "阿拉伯语 (科威特)", "ar-LB": "阿拉伯语 (黎巴嫩)", "ar-LY": "阿拉伯语 (利比亚)", "ar-MA": "阿拉伯语 (摩洛哥)",
        "ar-OM": "阿拉伯语 (阿曼)", "ar-QA": "阿拉伯语 (卡塔尔)", "ar-SA": "阿拉伯语 (沙特阿拉伯)", "ar-SY": "阿拉伯语 (叙利亚)",
        "ar-TN": "阿拉伯语 (突尼斯)", "ar-YE": "阿拉伯语 (也门)", "az-AZ": "阿塞拜疆语 (阿塞拜疆)", "bg-BG": "保加利亚语 (保加利亚)",
        "bn-BD": "孟加拉语 (孟加拉国)", "bn-IN": "孟加拉语 (印度)", "bs-BA": "波斯尼亚语 (波黑)", "ca-ES": "加泰罗尼亚语 (西班牙)",
        "cs-CZ": "捷克语 (捷克共和国)", "cy-GB": "威尔士语 (英国)", "da-DK": "丹麦语 (丹麦)", "de-AT": "德语 (奥地利)",
        "de-CH": "德语 (瑞士)", "de-DE": "德语 (德国)", "el-GR": "希腊语 (希腊)", "en-AU": "英语 (澳大利亚)",
        "en-CA": "英语 (加拿大)", "en-GB": "英语 (英国)", "en-HK": "英语 (香港)", "en-IE": "英语 (爱尔兰)",
        "en-IN": "英语 (印度)", "en-KE": "英语 (肯尼亚)", "en-NG": "英语 (尼日利亚)", "en-NZ": "英语 (新西兰)",
        "en-PH": "英语 (菲律宾)", "en-SG": "英语 (新加坡)", "en-TZ": "英语 (坦桑尼亚)", "en-US": "英语 (美国)",
        "en-ZA": "英语 (南非)", "es-AR": "西班牙语 (阿根廷)", "es-BO": "西班牙语 (玻利维亚)", "es-CL": "西班牙语 (智利)",
        "es-CO": "西班牙语 (哥伦比亚)", "es-CR": "西班牙语 (哥斯达黎加)", "es-CU": "西班牙语 (古巴)", "es-DO": "西班牙语 (多米尼加)",
        "es-EC": "西班牙语 (厄瓜多尔)", "es-ES": "西班牙语 (西班牙)", "es-GQ": "西班牙语 (赤道几内亚)", "es-GT": "西班牙语 (危地马拉)",
        "es-HN": "西班牙语 (洪都拉斯)", "es-MX": "西班牙语 (墨西哥)", "es-NI": "西班牙语 (尼加拉瓜)", "es-PA": "西班牙语 (巴拿马)",
        "es-PE": "西班牙语 (秘鲁)", "es-PR": "西班牙语 (波多黎各)", "es-PY": "西班牙语 (巴拉圭)", "es-SV": "西班牙语 (萨尔瓦多)",
        "es-US": "西班牙语 (美国)", "es-UY": "西班牙语 (乌拉圭)", "es-VE": "西班牙语 (委内瑞拉)", "et-EE": "爱沙尼亚语 (爱沙尼亚)",
        "fa-IR": "波斯语 (伊朗)", "fi-FI": "芬兰语 (芬兰)", "fil-PH": "菲律宾语 (菲律宾)", "fr-BE": "法语 (比利时)",
        "fr-CA": "法语 (加拿大)", "fr-CH": "法语 (瑞士)", "fr-FR": "法语 (法国)", "ga-IE": "爱尔兰语 (爱尔兰)",
        "gl-ES": "加利西亚语 (西班牙)", "gu-IN": "古吉拉特语 (印度)", "he-IL": "希伯来语 (以色列)", "hi-IN": "印地语 (印度)",
        "hr-HR": "克罗地亚语 (克罗地亚)", "hu-HU": "匈牙利语 (匈牙利)", "id-ID": "印尼语 (印度尼西亚)", "is-IS": "冰岛语 (冰岛)",
        "it-IT": "意大利语 (意大利)", "ja-JP": "日语 (日本)", "jv-ID": "爪哇语 (印度尼西亚)", "ka-GE": "格鲁吉亚语 (格鲁吉亚)",
        "kk-KZ": "哈萨克语 (哈萨克斯坦)", "km-KH": "高棉语 (柬埔寨)", "kn-IN": "卡纳达语 (印度)", "ko-KR": "韩语 (韩国)",
        "lo-LA": "老挝语 (老挝)", "lt-LT": "立陶宛语 (立陶宛)", "lv-LV": "拉脱维亚语 (拉脱维亚)", "mk-MK": "马其顿语 (北马其顿)",
        "ml-IN": "马拉雅拉姆语 (印度)", "mn-MN": "蒙古语 (蒙古)", "mr-IN": "马拉地语 (印度)", "ms-MY": "马来语 (马来西亚)",
        "mt-MT": "马耳他语 (马耳他)", "my-MM": "缅甸语 (缅甸)", "nb-NO": "挪威语 (博克马尔)", "ne-NP": "尼泊尔语 (尼泊尔)",
        "nl-BE": "荷兰语 (比利时)", "nl-NL": "荷兰语 (荷兰)", "pl-PL": "波兰语 (波兰)", "ps-AF": "普什图语 (阿富汗)",
        "pt-BR": "葡萄牙语 (巴西)", "pt-PT": "葡萄牙语 (葡萄牙)", "ro-RO": "罗马尼亚语 (罗马尼亚)", "ru-RU": "俄语 (俄罗斯)",
        "si-LK": "僧伽罗语 (斯里兰卡)", "sk-SK": "斯洛伐克语 (斯洛伐克)", "sl-SI": "斯洛文尼亚语 (斯洛文尼亚)", "so-SO": "索马里语 (索马里)",
        "sq-AL": "阿尔巴尼亚语 (阿尔巴尼亚)", "sr-RS": "塞尔维亚语 (塞尔维亚)", "su-ID": "巽他语 (印度尼西亚)", "sv-SE": "瑞典语 (瑞典)",
        "sw-KE": "斯瓦希里语 (肯尼亚)", "sw-TZ": "斯瓦希里语 (坦桑尼亚)", "ta-IN": "泰米尔语 (印度)", "ta-LK": "泰米尔语 (斯里兰卡)",
        "ta-MY": "泰米尔语 (马来西亚)", "ta-SG": "泰米尔语 (新加坡)", "te-IN": "泰卢固语 (印度)", "th-TH": "泰语 (泰国)",
        "tr-TR": "土耳其语 (土耳其)", "uk-UA": "乌克兰语 (乌克兰)", "ur-IN": "乌尔都语 (印度)", "ur-PK": "乌尔都语 (巴基斯坦)",
        "uz-UZ": "乌兹别克语 (乌兹别克斯坦)", "vi-VN": "越南语 (越南)", "zh-CN": "中文 (中国大陆)", "zh-HK": "中文 (香港)",
        "zh-TW": "中文 (台湾)", "zu-ZA": "祖鲁语 (南非)"
    }
    
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
        if not isinstance(new_data.get('port'), int) or not isinstance(new_data.get('openai_voice_map'), dict):
            return jsonify({"error": "Invalid data format"}), 400
        
        # 更新全局变量中的音色映射，使其立即生效
        config['openai_voice_map'] = new_data['openai_voice_map']
        
        # 更新端口号到要保存的完整配置中
        config['port'] = new_data['port']
        
        # 将更新后的完整配置保存到文件
        save_config_to_file(config)
        
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
        sanitized_text = text.replace('\n', ', ').strip()
        logger.info(f"Request voice: '{voice_name}', Mapped to: '{final_voice}', Text: '{sanitized_text[:50]}...'")

        communicate = edge_tts.Communicate(sanitized_text, final_voice)
        audio_buffer = BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])
        
        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0:
            return jsonify({"error": {"message": f"No audio received for voice {final_voice}."}}), 500
        
        return send_file(audio_buffer, mimetype='audio/mpeg', as_attachment=False)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return jsonify({"error": {"message": "Internal server error."}}), 500

# --- 应用启动 ---
if __name__ == '__main__':
    initialize_config()
    parse_voices()
    port = int(config.get('port', 5050))
    logger.info(f"Loaded {len(ALL_VOICES)} voices. Server starting on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)