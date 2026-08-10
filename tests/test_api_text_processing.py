import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import app as service


class ApiTextProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service.parse_voices()

    def setUp(self):
        self.original_config = service.config
        self.original_stream = service.generate_streaming_audio_sync
        self.original_run_official = service.run_tts_official_first
        self.original_chunk_size = service.CHUNK_SIZE
        self.original_sync_chunks = service.SYNC_CHUNKS
        self.original_concurrency = service.MAX_CONCURRENT_REQUESTS

    def tearDown(self):
        service.config = self.original_config
        service.generate_streaming_audio_sync = self.original_stream
        service.run_tts_official_first = self.original_run_official
        service.CHUNK_SIZE = self.original_chunk_size
        service.SYNC_CHUNKS = self.original_sync_chunks
        service.MAX_CONCURRENT_REQUESTS = self.original_concurrency

    def test_streaming_api_uses_cleaned_paragraph_chunks(self):
        captured_chunks = []
        service.config = {
            "api_token": "",
            "sync_api_filtering": True,
            "default_cleaning_options": {
                "remove_markdown": True,
                "remove_emoji": True,
                "no_urls": True,
                "no_line_breaks": True,
                "custom_keywords": "",
            },
            "openai_voice_map": {"shimmer": "zh-CN-XiaoxiaoNeural"},
        }
        service.CHUNK_SIZE = 400
        service.SYNC_CHUNKS = 1
        service.MAX_CONCURRENT_REQUESTS = 1

        def fake_stream(text_chunks, *args, **kwargs):
            captured_chunks.extend(text_chunks)
            yield b"ID3"

        service.generate_streaming_audio_sync = fake_stream

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "**血糖占比80.7%**（标准差1.67 mmol/L）。\n\n详情：https://example.com 😀",
                    "voice": "shimmer",
                    "stream": True,
                },
            )
            body = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "audio/mpeg")
        self.assertEqual(body, b"ID3")
        self.assertEqual(response.headers["X-TTS-Chunks"], "1")
        self.assertEqual(response.headers["X-TTS-Chunk-Size"], "400")
        self.assertEqual(
            captured_chunks,
            ["血糖占比80.7%（标准差1.67 mmol/L）。\n\n详情："],
        )

    def test_api_forwards_supported_style_role_and_degree(self):
        captured = {}
        service.config = {
            "api_token": "",
            "sync_api_filtering": False,
            "openai_voice_map": {},
        }

        def fake_stream(text_chunks, voice, *args, **kwargs):
            captured["chunks"] = text_chunks
            captured["voice"] = voice
            captured["args"] = args
            yield b"ID3"

        service.generate_streaming_audio_sync = fake_stream

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "角色与情绪测试。",
                    "voice": "zh-CN-YunxiNeural",
                    "style": "cheerful",
                    "role": "YoungAdultMale",
                    "style_degree": 1.4,
                    "speed": 1.1,
                    "pitch": 0.95,
                    "strict_capabilities": True,
                    "stream": True,
                },
            )
            response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-TTS-Voice"], "zh-CN-YunxiNeural")
        self.assertEqual(response.headers["X-TTS-Style"], "cheerful")
        self.assertEqual(response.headers["X-TTS-Role"], "YoungAdultMale")
        self.assertEqual(captured["voice"], "zh-CN-YunxiNeural")
        self.assertEqual(captured["args"][2:7], ("cheerful", "YoungAdultMale", 1.4, 1.1, 0.95))

    def test_api_rejects_unsupported_style_in_strict_mode(self):
        service.config = {
            "api_token": "",
            "sync_api_filtering": False,
            "openai_voice_map": {},
        }

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "不支持的风格。",
                    "voice": "en-US-Ava:DragonHDLatestNeural",
                    "style": "cheerful",
                    "strict_capabilities": True,
                    "stream": True,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support style", response.get_json()["error"]["message"])

    def test_api_rejects_unsafe_chunking_and_concurrency_values(self):
        service.config = {
            "api_token": "",
            "sync_api_filtering": False,
            "openai_voice_map": {},
        }

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "参数验证。",
                    "voice": "zh-CN-XiaoxiaoNeural",
                    "stream": True,
                    "max_concurrent_requests": 1000,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("max_concurrent_requests", response.get_json()["error"]["message"])

    def test_non_streaming_api_returns_502_when_every_chunk_fails(self):
        service.config = {
            "api_token": "",
            "sync_api_filtering": False,
            "openai_voice_map": {},
        }

        async def fake_run_official(text_chunks, *args, **kwargs):
            return [None] * len(text_chunks)

        service.run_tts_official_first = fake_run_official

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "上游连接失败时不应返回静音成功文件。",
                    "voice": "zh-CN-XiaoxiaoNeural",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("All TTS chunks failed", response.get_json()["error"]["message"])

    def test_standard_openai_request_applies_complete_saved_preset(self):
        captured = {}
        service.config = {
            "api_token": "",
            "sync_api_filtering": False,
            "default_cleaning_options": {},
            "openai_voice_map": {"shimmer": "zh-CN-XiaoxiaoNeural"},
            "openai_voice_presets": {
                "shimmer": {
                    "voice": "zh-CN-YunxiNeural",
                    "style": "cheerful",
                    "role": "YoungAdultMale",
                    "style_degree": 1.35,
                    "speed": 1.2,
                    "pitch": 0.9,
                    "strict_capabilities": True,
                    "cleaning_options": {
                        "remove_markdown": True,
                        "remove_emoji": True,
                        "no_urls": True,
                        "no_line_breaks": False,
                        "custom_keywords": "",
                    },
                }
            },
        }

        def fake_stream(text_chunks, voice, *args, **kwargs):
            captured["chunks"] = text_chunks
            captured["voice"] = voice
            captured["args"] = args
            yield b"ID3"

        service.generate_streaming_audio_sync = fake_stream

        with service.app.test_client() as client:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": "**预设测试80.7%** 😀",
                    "voice": "shimmer",
                    "speed": 1.0,
                    "stream": True,
                },
            )
            response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-TTS-Preset"], "shimmer")
        self.assertEqual(captured["voice"], "zh-CN-YunxiNeural")
        self.assertEqual(captured["chunks"], ["预设测试80.7%"])
        self.assertEqual(
            captured["args"][2:7],
            ("cheerful", "YoungAdultMale", 1.35, 1.2, 0.9),
        )

    def test_webui_can_save_complete_openai_voice_preset(self):
        service.config = {
            "api_token": "",
            "openai_voice_map": {"shimmer": "zh-CN-XiaoxiaoNeural"},
            "openai_voice_presets": {},
            "custom_voices": {},
        }
        payload = {
            "voice": "zh-CN-YunxiNeural",
            "style": "cheerful",
            "role": "YoungAdultMale",
            "style_degree": 1.4,
            "speed": 1.15,
            "pitch": 0.95,
            "cleaning_options": {
                "remove_markdown": True,
                "remove_emoji": True,
                "no_urls": True,
                "no_line_breaks": False,
                "custom_keywords": "附注",
            },
        }

        with patch.object(service, "save_config_to_file") as save_mock:
            with service.app.test_client() as client:
                with client.session_transaction() as browser_session:
                    browser_session["logged_in"] = True
                response = client.post(
                    "/v1/openai-voice-presets/shimmer",
                    json=payload,
                )

        self.assertEqual(response.status_code, 200)
        preset = response.get_json()["preset"]
        self.assertEqual(preset["voice"], "zh-CN-YunxiNeural")
        self.assertEqual(preset["style"], "cheerful")
        self.assertEqual(preset["speed"], 1.15)
        self.assertEqual(preset["cleaning_options"]["custom_keywords"], "附注")
        self.assertEqual(
            service.config["openai_voice_map"]["shimmer"],
            "zh-CN-YunxiNeural",
        )
        save_mock.assert_called_once()


class MicrosoftRequestReuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_keeps_audio_order_with_background_generation(self):
        class FakeCommunicate:
            def __init__(self, text, *args, **kwargs):
                self.text = text

            async def stream(self):
                yield {"type": "audio", "data": self.text.encode("utf-8")}

        with patch.object(service.edge_tts, "Communicate", FakeCommunicate):
            audio = [
                chunk
                async for chunk in service.generate_streaming_audio_async(
                    ["第一段", "第二段", "第三段"],
                    "zh-CN-XiaoxiaoNeural",
                    sync_chunks=1,
                    max_concurrent_requests=3,
                )
            ]

        self.assertEqual(audio, [part.encode("utf-8") for part in ["第一段", "第二段", "第三段"]])

    async def test_official_chunks_share_endpoint_lookup_and_http_session(self):
        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        fake_session = FakeSession()
        endpoint = {"r": "region", "t": "token", "url": "https://example.test/tts"}
        endpoint_mock = AsyncMock(return_value=endpoint)
        tts_mock = AsyncMock(return_value=b"ID3-audio")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(service.aiohttp, "ClientSession", return_value=fake_session):
                with patch.object(service, "get_microsoft_endpoint", endpoint_mock):
                    with patch.object(service, "tts_with_microsoft_api", tts_mock):
                        results = await service.run_tts_official_first(
                            ["第一段。", "第二段。", "第三段。"],
                            "zh-CN-XiaoxiaoNeural",
                            temp_dir,
                            max_concurrent_requests=3,
                        )

        self.assertEqual(len(results), 3)
        endpoint_mock.assert_awaited_once_with(fake_session)
        self.assertEqual(tts_mock.await_count, 3)
        for call in tts_mock.await_args_list:
            self.assertIs(call.kwargs["endpoint"], endpoint)
            self.assertIs(call.kwargs["client_session"], fake_session)


if __name__ == "__main__":
    unittest.main()
