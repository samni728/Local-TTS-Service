import json
import unittest
from pathlib import Path

from voice_catalog import build_voice_catalog, catalog_metadata, filter_voices


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VoiceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        edge_text = (PROJECT_ROOT / "tts_data" / "voices_list.txt").read_text(encoding="utf-8")
        locales = json.loads(
            (PROJECT_ROOT / "tts_data" / "locales_map.json").read_text(encoding="utf-8")
        )
        azure_text = (
            PROJECT_ROOT
            / "docs"
            / "Azure语音的语言和语音支持 - Foundry Tools - Microsoft Learn.md"
        ).read_text(encoding="utf-8")
        cls.voices = build_voice_catalog(edge_text, locales, azure_text)
        cls.index = {voice["name"]: voice for voice in cls.voices}

    def test_imports_azure_document_and_edge_baseline(self):
        metadata = catalog_metadata(self.voices)

        self.assertGreaterEqual(metadata["total"], 750)
        self.assertGreaterEqual(metadata["azure_documented"], 750)
        self.assertEqual(metadata["edge_available"], 322)

    def test_chinese_and_english_locales_sort_first(self):
        locales = list(dict.fromkeys(voice["locale"] for voice in self.voices))

        first_non_priority = next(
            index
            for index, locale in enumerate(locales)
            if not locale.startswith(("zh-", "en-"))
        )
        self.assertTrue(all(locale.startswith(("zh-", "en-")) for locale in locales[:first_non_priority]))

    def test_voice_styles_roles_gender_and_source_are_extracted(self):
        yunxi = self.index["zh-CN-YunxiNeural"]

        self.assertEqual(yunxi["gender"], "Male")
        self.assertIn("cheerful", yunxi["styles"])
        self.assertIn("YoungAdultMale", yunxi["roles"])
        self.assertTrue(yunxi["supports_style_degree"])
        self.assertTrue(yunxi["edge_available"])
        self.assertTrue(yunxi["azure_documented"])

    def test_new_hd_and_mai_voices_are_available_in_catalog(self):
        self.assertEqual(
            self.index["en-US-Ava:DragonHDLatestNeural"]["voice_type"],
            "Neural HD",
        )
        self.assertEqual(
            self.index["tr-TR-Aydın:MAI-Voice-2"]["voice_type"],
            "MAI Voice",
        )

    def test_filtering_combines_locale_gender_style_and_role(self):
        matches = filter_voices(
            self.voices,
            locale="zh-CN",
            gender="female",
            style="cheerful",
            role="YoungAdultFemale",
        )

        self.assertTrue(matches)
        self.assertTrue(all(voice["gender"] == "Female" for voice in matches))
        self.assertTrue(all("cheerful" in voice["styles"] for voice in matches))
        self.assertTrue(all("YoungAdultFemale" in voice["roles"] for voice in matches))


if __name__ == "__main__":
    unittest.main()
