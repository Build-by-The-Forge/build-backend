"""Malware scanning against the real stack (M3-D PR 6, ruling 7): every
upload waits in quarantine for clamd, a clean one is released, the EICAR
test file is rejected and never processed, and with the scanner stopped
uploads stay quarantined and nothing processes them."""

import time

import pytest

from boundary.conftest import create_source, upload

# The EICAR anti-malware test file: harmless, and detected by every scanner.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
SCAN_TIMEOUT = 120


def asset(backend, tenant, asset_id: str) -> dict:
    response = backend.get(f"/content/assets/{asset_id}", headers=tenant.h("lecturer"))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def settles(backend, tenant, asset_id: str, timeout: float = SCAN_TIMEOUT) -> str:
    deadline = time.time() + timeout
    status = asset(backend, tenant, asset_id)["ingestion_status"]
    while status == "quarantined" and time.time() < deadline:
        time.sleep(1)
        status = asset(backend, tenant, asset_id)["ingestion_status"]
    return status


def uploaded(backend, tenant, document: bytes) -> dict:
    response = upload(backend, tenant, create_source(backend, tenant), document)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    # Every new document starts in quarantine, whatever its bytes.
    assert data["ingestion_status"] == "quarantined", data
    return data


def test_m3d_the_eicar_file_is_rejected_and_never_processed(backend, tenant_a):
    data = uploaded(backend, tenant_a, EICAR)
    assert settles(backend, tenant_a, data["id"]) == "rejected"
    refused = backend.post(f"/content/assets/{data['id']}/jobs", json={}, headers=tenant_a.h("lecturer"))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "DOCUMENT_REJECTED"
    # The uploader is never told the signature's name.
    assert "Eicar" not in refused.text and "EICAR" not in refused.text


@pytest.mark.scanner_down
def test_m3d_with_the_scanner_stopped_uploads_stay_quarantined_and_unprocessed(backend, tenant_a):
    data = uploaded(backend, tenant_a, b"%PDF-1.4\n% scanner down " + str(time.time()).encode() * 10)
    # Several scan passes run meanwhile; none can accept it.
    assert settles(backend, tenant_a, data["id"], timeout=20) == "quarantined"
    refused = backend.post(f"/content/assets/{data['id']}/jobs", json={}, headers=tenant_a.h("lecturer"))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "DOCUMENT_NOT_SCANNED"
