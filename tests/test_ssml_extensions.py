import unittest

import app as service


class SsmlExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service.parse_voices()

    def test_style_role_and_degree_share_one_express_as_element(self):
        ssml = service.generate_ssml(
            "血糖 < 3.0 & 需要关注",
            "zh-CN-XiaomoNeural",
            style="cheerful",
            role="YoungAdultFemale",
            style_degree=1.35,
            speed=1.1,
            pitch=0.9,
        )

        self.assertEqual(ssml.count("<mstts:express-as"), 1)
        self.assertIn('style="cheerful"', ssml)
        self.assertIn('role="YoungAdultFemale"', ssml)
        self.assertIn('styledegree="1.35"', ssml)
        self.assertIn('rate="+10%"', ssml)
        self.assertIn('pitch="-10%"', ssml)
        self.assertIn('xml:lang="zh-CN"', ssml)
        self.assertIn("血糖 &lt; 3.0 &amp; 需要关注", ssml)

    def test_auto_voice_selection_respects_gender_style_and_role(self):
        voice_name, voice = service._resolve_voice(
            {
                "voice": "auto",
                "locale": "zh-CN",
                "gender": "Female",
            },
            style="cheerful",
            role="YoungAdultFemale",
        )

        self.assertEqual(voice_name, voice["name"])
        self.assertEqual(voice["gender"], "Female")
        self.assertIn("cheerful", voice["styles"])
        self.assertIn("YoungAdultFemale", voice["roles"])

    def test_paragraph_boundaries_become_explicit_ssml_pauses(self):
        ssml = service.generate_ssml(
            "第一段。\n\n第二段。",
            "zh-CN-XiaoxiaoNeural",
        )

        self.assertIn('第一段。<break time="320ms"/>第二段。', ssml)

    def test_strict_validation_rejects_unsupported_style(self):
        with self.assertRaisesRegex(ValueError, "does not support style"):
            service._resolve_voice(
                {
                    "voice": "en-US-Ava:DragonHDLatestNeural",
                    "strict_capabilities": True,
                },
                style="cheerful",
            )


if __name__ == "__main__":
    unittest.main()
