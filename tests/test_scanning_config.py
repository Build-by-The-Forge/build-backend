"""Malware scanning's settings (M3-D PR 6): staging and production refuse to
start without a scanner, and the scanner must read at least what an upload
may be, or a large document would never be accepted."""

import pytest

from app.core.config import Settings

STRICT = {
    "auth_jwt_secret": "j" * 40,
    "ai_service_url": "https://ai-service.internal",
    "backend_to_ai_secret": "b" * 40,
    "ai_to_backend_secret": "a" * 40,
}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_strict_environments_need_a_scanner(environment):
    with pytest.raises(ValueError, match="CLAMAV_HOST is required"):
        Settings(_env_file=None, app_environment=environment, **STRICT)
    assert Settings(_env_file=None, app_environment=environment, clamav_host="clamav", **STRICT).clamav_host == "clamav"


def test_development_starts_without_one_and_nothing_is_accepted_then():
    # The worker then defers every scan: documents stay quarantined.
    assert Settings(_env_file=None, app_environment="development").clamav_host is None


def test_the_scanner_reads_at_least_an_upload():
    with pytest.raises(ValueError, match="SCAN_MAX_BYTES must be at least MAX_UPLOAD_BYTES"):
        Settings(_env_file=None, app_environment="development", max_upload_bytes=2048, scan_max_bytes=1024)
