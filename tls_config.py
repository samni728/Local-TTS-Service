"""Cross-platform TLS trust configuration for outbound TTS requests."""

from __future__ import annotations

import os
from pathlib import Path


def configure_tls_trust() -> str:
    """Configure Python to use an explicit CA bundle or the OS trust store.

    ``truststore`` maps to Keychain on macOS, CryptoAPI on Windows, and the
    OpenSSL/system CA store on Linux.  An explicit bundle remains available
    for VPS installations behind a private HTTPS-inspection proxy.
    """

    ca_bundle = os.environ.get("TTS_CA_BUNDLE", "").strip()
    if ca_bundle:
        bundle_path = Path(ca_bundle).expanduser()
        if not bundle_path.is_file():
            raise RuntimeError(f"TTS_CA_BUNDLE does not exist: {bundle_path}")
        os.environ["SSL_CERT_FILE"] = str(bundle_path)
        return f"custom CA bundle ({bundle_path})"

    try:
        import truststore
    except ImportError:
        return "Python default CA bundle"

    truststore.inject_into_ssl()
    return "operating-system trust store"


def is_certificate_verification_error(error: BaseException) -> bool:
    """Return whether an exception chain represents TLS verification failure."""

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        message = str(current).upper()
        if (
            "CERTIFICATE_VERIFY_FAILED" in message
            or "CERTIFICATE VERIFY FAILED" in message
            or "CERTIFICATE VERIFICATION FAILED" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def certificate_error_message(error: BaseException) -> str:
    """Build an actionable error without suggesting unsafe SSL disabling."""

    return (
        "Microsoft TLS 证书校验失败。服务仍保持安全校验；请将代理/公司 CA 安装到系统信任库，"
        "或通过 TTS_CA_BUNDLE=/absolute/path/to/ca.pem 指定 CA 文件。"
        f" 原始错误: {error}"
    )
