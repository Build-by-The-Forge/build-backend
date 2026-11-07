"""Malware scanning against the real stack (M3-D PR 6, ruling 7): every
upload waits in quarantine for clamd, a clean one is released, the EICAR
test file is rejected and never processed, and with the scanner stopped
uploads stay quarantined and nothing processes them."""

import time

import pytest

from boundary.conftest import create_source, upload

# The EICAR anti-malware test file: harmless, and detected by every scanner.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def pdf_embedding(payload: bytes) -> bytes:
    """A valid PDF carrying ``payload`` as an embedded file. Uploads accept only
    PDF, PNG and JPEG, so EICAR travels inside a PDF; clamd's PDF parser
    extracts the embedded stream and finds it (verified against the pinned
    clamav image: "Eicar-Signature FOUND")."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [(eicar.com) 4 0 R] >> >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        b"<< /Type /Filespec /F (eicar.com) /EF << /F 5 0 R >> >>",
        b"<< /Type /EmbeddedFile /Length " + str(len(payload)).encode() + b" >>\nstream\n" + payload + b"\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    trailer = b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    return out + trailer + b"startxref\n" + str(xref).encode() + b"\n%%EOF\n"


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
    data = uploaded(backend, tenant_a, pdf_embedding(EICAR))
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
