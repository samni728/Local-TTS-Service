"""Build a capability-aware Azure/Edge TTS voice catalog.

The checked-in Edge voice list remains the known-working baseline. The Azure
language-support document augments it with newer voices plus per-voice styles
and roles. No network access is required at service startup.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


# Microsoft style values found in the Azure language-support table. Sorting by
# length before matching lets us recover values from flattened copied tables
# where separators between adjacent style names were lost.
KNOWN_STYLES = (
    "adventurous",
    "advertisement-upbeat",
    "affectionate",
    "anger",
    "angry",
    "anxious",
    "assassin",
    "assistant",
    "callcenter",
    "calm",
    "captain",
    "caringempathy",
    "cavalier",
    "chat",
    "chat-casual",
    "cheerful",
    "comforting",
    "complaining",
    "confused",
    "confusion",
    "conversation",
    "curious",
    "customer-service",
    "customerservice",
    "cute",
    "cutesy",
    "debating",
    "depressed",
    "determination",
    "determined",
    "disappointed",
    "disgruntled",
    "disgust",
    "disgusted",
    "documentary-narration",
    "embarrassed",
    "embarrassment",
    "empathetic",
    "encouraging",
    "envious",
    "excited",
    "excitement",
    "fear",
    "fearful",
    "friendly",
    "friendlycheerful",
    "funny",
    "game-narrator",
    "generalconversation",
    "gentle",
    "geomancer",
    "guilty",
    "happiness",
    "happy",
    "hope",
    "hopeful",
    "jealous",
    "jealousy",
    "joy",
    "joyful",
    "learning",
    "live-commercial",
    "livecommercial",
    "lonely",
    "lyrical",
    "media",
    "narration",
    "narration-professional",
    "narration-relaxed",
    "nervous",
    "neutral",
    "news",
    "newscast",
    "newscast-casual",
    "newscast-formal",
    "nostalgic",
    "persuasive",
    "poet",
    "poetry-reading",
    "prince",
    "professional",
    "reflective",
    "regret",
    "regretful",
    "relief",
    "relieved",
    "sad",
    "saddisappointed",
    "sadness",
    "sales",
    "sentimental",
    "serious",
    "shouting",
    "shy",
    "softvoice",
    "sorry",
    "sports-commentary",
    "sports-commentary-excited",
    "story",
    "story-telling",
    "strict",
    "surprise",
    "surprised",
    "terrified",
    "tired",
    "unfriendly",
    "voice-assistant",
    "whispering",
)

KNOWN_ROLES = (
    "Boy",
    "Girl",
    "Narrator",
    "OlderAdultFemale",
    "OlderAdultMale",
    "SeniorFemale",
    "SeniorMale",
    "YoungAdultFemale",
    "YoungAdultMale",
)

_VOICE_PATTERN = re.compile(
    r"\b[a-z]{2,3}(?:-[A-Za-z0-9\u00c0-\u024f]{2,40}){2,5}"
    r"(?:Neural|:(?:[A-Za-z0-9-]*Neural|MAI-Voice-\d+(?:-Flash)?))\b"
)
_STYLE_PATTERN = re.compile(
    "|".join(re.escape(value) for value in sorted(KNOWN_STYLES, key=len, reverse=True))
)
_ROLE_PATTERN = re.compile(
    "|".join(re.escape(value) for value in sorted(KNOWN_ROLES, key=len, reverse=True))
)

_GENDER_ALIASES = {
    "female": "Female",
    "女性": "Female",
    "女": "Female",
    "male": "Male",
    "男性": "Male",
    "男": "Male",
    "neutral": "Neutral",
    "中性": "Neutral",
}

_TYPE_PRIORITY = {
    "Standard": 0,
    "Multilingual": 1,
    "Neural HD": 2,
    "Neural HD Flash": 3,
    "Neural HD Omni": 4,
    "MAI Voice": 5,
}


def normalize_gender(value: str | None) -> str:
    if not value:
        return "Unknown"
    return _GENDER_ALIASES.get(value.strip().lower(), value.strip().title())


def infer_voice_type(name: str) -> str:
    if "MAI-Voice" in name:
        return "MAI Voice"
    if "DragonHDOmni" in name:
        return "Neural HD Omni"
    if "DragonHDFlash" in name:
        return "Neural HD Flash"
    if "DragonHD" in name:
        return "Neural HD"
    if "Multilingual" in name:
        return "Multilingual"
    return "Standard"


def infer_locale(name: str, locale_names: dict[str, str]) -> str:
    matching = [locale for locale in locale_names if name.lower().startswith(f"{locale.lower()}-")]
    if matching:
        return max(matching, key=len)

    parts = name.split("-")
    if len(parts) >= 3:
        if len(parts[1]) == 4 and len(parts) >= 4:
            return "-".join(parts[:3])
        return "-".join(parts[:2])
    return parts[0]


def _country_label(locale: str, locale_display_name: str) -> str:
    match = re.search(r"[（(]([^）)]+)[）)]", locale_display_name)
    if match:
        return match.group(1)
    parts = locale.split("-")
    return parts[-1].upper() if len(parts) > 1 else locale.upper()


def _short_name(name: str, locale: str) -> str:
    prefix = f"{locale}-"
    return name[len(prefix) :] if name.lower().startswith(prefix.lower()) else name


def _base_voice(
    name: str,
    locale_names: dict[str, str],
    *,
    gender: str = "Unknown",
) -> dict:
    locale = infer_locale(name, locale_names)
    locale_display_name = locale_names.get(locale, locale)
    return {
        "name": name,
        "short_name": _short_name(name, locale),
        "locale": locale,
        "locale_name": locale_display_name,
        "country": _country_label(locale, locale_display_name),
        "gender": normalize_gender(gender),
        "voice_type": infer_voice_type(name),
        "styles": [],
        "roles": [],
        "supports_style": False,
        "supports_role": False,
        "supports_style_degree": False,
        "is_multilingual": "Multilingual" in name,
        "edge_available": False,
        "azure_documented": False,
        "content_categories": [],
        "personalities": [],
    }


def _parse_edge_voices(text: str, locale_names: dict[str, str]) -> dict[str, dict]:
    voices: dict[str, dict] = {}
    for line in text.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name, gender = parts[0], parts[1]
        if "Neural" not in name:
            continue
        voice = _base_voice(name, locale_names, gender=gender)
        voice["edge_available"] = True
        if len(parts) >= 3:
            voice["content_categories"] = [item.strip() for item in parts[2].split(",") if item.strip()]
        if len(parts) >= 4:
            voice["personalities"] = [item.strip() for item in " ".join(parts[3:]).split(",") if item.strip()]
        voices[name] = voice
    return voices


def _parse_documented_voices(
    text: str,
    locale_names: dict[str, str],
) -> dict[str, dict]:
    matches = list(_VOICE_PATTERN.finditer(text))
    voices: dict[str, dict] = {}
    for index, match in enumerate(matches):
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.end() : segment_end]
        conversion_markers = [
            position
            for marker in ("❌", "✅")
            if (position := segment.find(marker)) >= 0
        ]
        segment = segment[: min(conversion_markers)] if conversion_markers else segment

        gender_match = re.search(
            r"[（(]\s*(女性|男性|女|男|中性|Female|Male|Neutral)(?:\s*[,，][^）)]*)?\s*[）)]",
            segment,
            flags=re.IGNORECASE,
        )
        styles_match = re.search(r"风格\s*(.*?)\s*角色", segment)
        roles_match = re.search(r"角色\s*(.*)$", segment)

        styles = _STYLE_PATTERN.findall(styles_match.group(1)) if styles_match else []
        roles = _ROLE_PATTERN.findall(roles_match.group(1)) if roles_match else []
        voice = _base_voice(
            match.group(0),
            locale_names,
            gender=gender_match.group(1) if gender_match else "Unknown",
        )
        voice.update(
            {
                "styles": list(dict.fromkeys(styles)),
                "roles": list(dict.fromkeys(roles)),
                "supports_style": bool(styles),
                "supports_role": bool(roles),
                "supports_style_degree": bool(styles),
                "azure_documented": True,
            }
        )
        voices[voice["name"]] = voice
    return voices


def _sort_key(voice: dict) -> tuple:
    locale = voice["locale"]
    language_priority = 0 if locale.startswith("zh-") else 1 if locale.startswith("en-") else 2
    gender_priority = {"Female": 0, "Male": 1, "Neutral": 2}.get(voice["gender"], 3)
    return (
        language_priority,
        voice["locale_name"],
        _TYPE_PRIORITY.get(voice["voice_type"], 99),
        gender_priority,
        voice["name"].casefold(),
    )


def build_voice_catalog(
    edge_voices_text: str,
    locale_names: dict[str, str],
    azure_document_text: str = "",
) -> list[dict]:
    edge_voices = _parse_edge_voices(edge_voices_text, locale_names)
    documented_voices = _parse_documented_voices(azure_document_text, locale_names)

    merged = documented_voices
    for name, edge_voice in edge_voices.items():
        if name not in merged:
            merged[name] = edge_voice
            continue
        documented = merged[name]
        documented["edge_available"] = True
        documented["content_categories"] = edge_voice["content_categories"]
        documented["personalities"] = edge_voice["personalities"]
        if documented["gender"] == "Unknown":
            documented["gender"] = edge_voice["gender"]
    return sorted(merged.values(), key=_sort_key)


def filter_voices(
    voices: Iterable[dict],
    *,
    locale: str | None = None,
    gender: str | None = None,
    style: str | None = None,
    role: str | None = None,
    voice_type: str | None = None,
    supports_style: bool = False,
    supports_role: bool = False,
    edge_available: bool = False,
    query: str | None = None,
) -> list[dict]:
    normalized_gender = normalize_gender(gender) if gender else None
    normalized_query = query.casefold().strip() if query else ""
    result = []
    for voice in voices:
        if locale and voice["locale"].casefold() != locale.casefold():
            continue
        if normalized_gender and voice["gender"] != normalized_gender:
            continue
        if style and style not in voice["styles"]:
            continue
        if role and role not in voice["roles"]:
            continue
        if voice_type and voice["voice_type"].casefold() != voice_type.casefold():
            continue
        if supports_style and not voice["supports_style"]:
            continue
        if supports_role and not voice["supports_role"]:
            continue
        if edge_available and not voice["edge_available"]:
            continue
        if normalized_query:
            haystack = " ".join(
                (
                    voice["name"],
                    voice["short_name"],
                    voice["locale_name"],
                    voice["country"],
                    " ".join(voice["styles"]),
                    " ".join(voice["roles"]),
                )
            ).casefold()
            if normalized_query not in haystack:
                continue
        result.append(voice)
    return result


def catalog_metadata(voices: Iterable[dict]) -> dict:
    voice_list = list(voices)
    return {
        "styles": sorted({style for voice in voice_list for style in voice["styles"]}),
        "roles": sorted({role for voice in voice_list for role in voice["roles"]}),
        "voice_types": sorted({voice["voice_type"] for voice in voice_list}, key=lambda item: _TYPE_PRIORITY.get(item, 99)),
        "genders": ["Female", "Male", "Neutral"],
        "total": len(voice_list),
        "edge_available": sum(1 for voice in voice_list if voice["edge_available"]),
        "azure_documented": sum(1 for voice in voice_list if voice["azure_documented"]),
    }
