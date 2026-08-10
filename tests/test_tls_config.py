import os
import tempfile
import unittest
from unittest.mock import patch

from tls_config import (
    certificate_error_message,
    configure_tls_trust,
    is_certificate_verification_error,
)


class TlsConfigTests(unittest.TestCase):
    def test_explicit_ca_bundle_is_supported_cross_platform(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as bundle:
            with patch.dict(os.environ, {"TTS_CA_BUNDLE": bundle.name}, clear=False):
                source = configure_tls_trust()
                self.assertIn("custom CA bundle", source)
                self.assertEqual(os.environ["SSL_CERT_FILE"], bundle.name)

    def test_missing_explicit_ca_bundle_fails_at_startup(self):
        with patch.dict(os.environ, {"TTS_CA_BUNDLE": "/missing/company-ca.pem"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                configure_tls_trust()

    def test_certificate_error_is_detected_through_exception_chain(self):
        try:
            try:
                raise ValueError("certificate verify failed: self-signed certificate in certificate chain")
            except ValueError as error:
                raise RuntimeError("connection failed") from error
        except RuntimeError as error:
            self.assertTrue(is_certificate_verification_error(error))
            self.assertIn("TTS_CA_BUNDLE", certificate_error_message(error))


if __name__ == "__main__":
    unittest.main()
