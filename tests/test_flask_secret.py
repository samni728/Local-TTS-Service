import os
import stat
import tempfile
import unittest
from unittest.mock import patch

import app as service


class FlaskSecretTests(unittest.TestCase):
    def test_explicit_environment_secret_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = os.path.join(temp_dir, "session-secret")
            with patch.dict(os.environ, {"FLASK_SECRET_KEY": "configured-secret"}):
                result = service.resolve_flask_secret_key(secret_path)
                secret_file_created = os.path.exists(secret_path)

        self.assertEqual(result, "configured-secret")
        self.assertFalse(secret_file_created)

    def test_empty_environment_secret_creates_and_reuses_persistent_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = os.path.join(temp_dir, "session-secret")
            with patch.dict(os.environ, {"FLASK_SECRET_KEY": ""}):
                first = service.resolve_flask_secret_key(secret_path)
                second = service.resolve_flask_secret_key(secret_path)
                file_mode = stat.S_IMODE(os.stat(secret_path).st_mode)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(file_mode & 0o077, 0)

    def test_login_works_when_legacy_env_has_no_flask_secret(self):
        original_secret = service.app.secret_key
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                secret_path = os.path.join(temp_dir, "session-secret")
                with patch.dict(
                    os.environ,
                    {"FLASK_SECRET_KEY": "", "WEBUI_PASSWORD": "correct-password"},
                ):
                    service.app.secret_key = service.resolve_flask_secret_key(secret_path)
                    with service.app.test_client() as client:
                        response = client.post(
                            "/login",
                            data={"password": "correct-password"},
                        )
                        with client.session_transaction() as browser_session:
                            logged_in = browser_session.get("logged_in")

            self.assertEqual(response.status_code, 302)
            self.assertTrue(logged_in)
        finally:
            service.app.secret_key = original_secret


if __name__ == "__main__":
    unittest.main()
