"""S3ObjectStorage against a real S3-compatible service.

CI runs SeaweedFS (scripts/seaweedfs_test_storage.sh) in the storage-gate
job. The tests are provider-neutral, so they can later check the production
provider too: a smaller compatibility gate, because a policy SeaweedFS
enforces is not proof that every provider enforces it.

Configuration: OBJECT_STORAGE_TEST_* (written by the script). With
OBJECT_STORAGE_TESTS_REQUIRED=1, as in CI, missing configuration is a
collection error rather than a skip, so the job cannot pass without running
these tests.
"""

import hashlib
import logging
import os
import uuid

import boto3
import httpx
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from app.domain.content.storage import (
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorageAccessDeniedError,
    ObjectStorageUnavailableError,
    ObjectTooLargeError,
)
from app.infrastructure.content.s3_object_storage import S3ObjectStorage, map_client_error

_ENV = "OBJECT_STORAGE_TEST_"
_NEEDED = ("ENDPOINT", "BUCKET_A", "BUCKET_B", "WRITER_A", "READER_A", "WRITER_B")
CONFIG = {name: os.getenv(_ENV + name) for name in (*_NEEDED, "REGION")}
CONFIGURED = all(CONFIG[name] for name in _NEEDED)

if os.getenv("OBJECT_STORAGE_TESTS_REQUIRED") == "1" and not CONFIGURED:
    missing = ", ".join(_ENV + name for name in _NEEDED if not CONFIG[name])
    raise RuntimeError(f"real object-storage tests are required, but {missing} are not set")

pytestmark = pytest.mark.skipif(not CONFIGURED, reason="OBJECT_STORAGE_TEST_* not set")

BODY = b"%PDF-1.7 course notes: 6CO2 + 6H2O -> C6H12O6 + 6O2? 100% \xe2\x88\x9a\n" * 64
SHA = hashlib.sha256(BODY).hexdigest()
RUN = f"tests/{uuid.uuid4().hex}"


def _credentials(name: str) -> tuple[str, str]:
    access, secret = CONFIG[name].split(":", 1)
    return access, secret


def _storage(identity: str, bucket: str, **overrides) -> S3ObjectStorage:
    access, secret = _credentials(identity)
    options = {
        "bucket": CONFIG[bucket],
        "endpoint_url": CONFIG["ENDPOINT"],
        "region": CONFIG["REGION"] or "us-east-1",
        "access_key_id": access,
        "secret_access_key": secret,
        "addressing_style": "path",
        "connect_timeout_seconds": 3,
        "read_timeout_seconds": 10,
        "max_attempts": 1,
    }
    options.update(overrides)
    return S3ObjectStorage(**options)


@pytest.fixture
def writer_a():
    return _storage("WRITER_A", "BUCKET_A")


@pytest.fixture
def reader_a():
    return _storage("READER_A", "BUCKET_A")


@pytest.fixture
def writer_b():
    return _storage("WRITER_B", "BUCKET_B")


@pytest.fixture
async def object_in_a(writer_a):
    """One stored object in bucket A, removed afterwards even if the test
    fails."""
    key = f"{RUN}/a/{uuid.uuid4().hex}"
    await writer_a.put(key, BODY, content_type="application/pdf")
    yield key
    await writer_a.delete(key)


@pytest.fixture
async def object_in_b(writer_b):
    key = f"{RUN}/b/{uuid.uuid4().hex}"
    await writer_b.put(key, b"bucket b only", content_type="text/plain")
    yield key
    await writer_b.delete(key)


async def _present(storage: S3ObjectStorage, key: str) -> bool:
    try:
        await storage.head(key)
        return True
    except ObjectNotFoundError:
        return False


# --- round trip and checksums ---------------------------------------------------------------


async def test_a_stored_object_round_trips_with_its_sha256(writer_a, reader_a):
    key = f"{RUN}/round-trip"
    try:
        stored = await writer_a.put(key, BODY, content_type="application/pdf")

        assert (stored.size_bytes, stored.sha256) == (len(BODY), SHA)
        info = await writer_a.head(key)
        assert (info.size_bytes, info.content_type, info.sha256) == (len(BODY), "application/pdf", SHA)
        assert await writer_a.get(key, expected_sha256=SHA, max_bytes=len(BODY)) == BODY
        assert await reader_a.get(key, expected_sha256=SHA, max_bytes=len(BODY)) == BODY
    finally:
        await writer_a.delete(key)


async def test_get_refuses_an_object_that_does_not_match_the_expected_sha256(reader_a, object_in_a):
    with pytest.raises(ObjectIntegrityError) as caught:
        await reader_a.get(object_in_a, expected_sha256="0" * 64, max_bytes=len(BODY))

    assert (caught.value.error_code, caught.value.is_retryable) == ("OBJECT_INTEGRITY_MISMATCH", False)


async def test_a_mismatched_expected_sha256_stores_nothing(writer_a):
    key = f"{RUN}/never-stored"

    with pytest.raises(ObjectIntegrityError):
        await writer_a.put(key, BODY, content_type="application/pdf", expected_sha256="f" * 64)

    assert not await _present(writer_a, key)


async def test_the_service_refuses_a_body_that_does_not_match_its_sha256_header(writer_a):
    # Corruption in transit, simulated by declaring the wrong SHA-256: the
    # service must refuse it, store nothing, and the adapter must map the
    # refusal to a retryable integrity error.
    access, secret = _credentials("WRITER_A")
    raw = boto3.session.Session().client(
        "s3",
        endpoint_url=CONFIG["ENDPOINT"],
        region_name=CONFIG["REGION"] or "us-east-1",
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 1},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    key = f"{RUN}/corrupted"
    wrong = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="  # base64 SHA-256 of something else

    with pytest.raises(ClientError) as caught:
        raw.put_object(Bucket=CONFIG["BUCKET_A"], Key=key, Body=BODY, ChecksumSHA256=wrong)

    mapped = map_client_error(caught.value)
    assert (mapped.error_code, mapped.is_retryable) == ("OBJECT_TRANSFER_CORRUPTED", True)
    assert not await _present(writer_a, key)


async def test_storing_the_same_bytes_again_is_safe(writer_a):
    key = f"{RUN}/retried"
    try:
        first = await writer_a.put(key, BODY, content_type="application/pdf")
        second = await writer_a.put(key, BODY, content_type="application/pdf")

        assert first == second
        assert await writer_a.get(key, expected_sha256=SHA, max_bytes=len(BODY)) == BODY
    finally:
        await writer_a.delete(key)


async def test_a_size_limit_is_enforced_on_read(reader_a, object_in_a):
    with pytest.raises(ObjectTooLargeError):
        await reader_a.get(object_in_a, expected_sha256=SHA, max_bytes=len(BODY) - 1)


# --- the read-only identity -----------------------------------------------------------------


async def test_the_read_only_identity_reads_and_inspects(reader_a, object_in_a):
    assert await reader_a.get(object_in_a, expected_sha256=SHA, max_bytes=len(BODY)) == BODY
    assert (await reader_a.head(object_in_a)).size_bytes == len(BODY)


async def test_the_read_only_identity_cannot_write_or_delete(reader_a, writer_a, object_in_a):
    new_key = f"{RUN}/written-by-reader"

    with pytest.raises(ObjectStorageAccessDeniedError):
        await reader_a.put(new_key, b"x", content_type="text/plain")
    with pytest.raises(ObjectStorageAccessDeniedError):
        await reader_a.delete(object_in_a)

    assert not await _present(writer_a, new_key)
    assert await _present(writer_a, object_in_a)


# --- bucket isolation, enforced by the service ----------------------------------------------


async def test_identities_cannot_reach_another_bucket(writer_a, writer_b, object_in_a, object_in_b):
    a_on_b = _storage("WRITER_A", "BUCKET_B")
    b_on_a = _storage("WRITER_B", "BUCKET_A")
    reader_on_b = _storage("READER_A", "BUCKET_B")

    for storage, key in ((a_on_b, object_in_b), (b_on_a, object_in_a), (reader_on_b, object_in_b)):
        with pytest.raises(ObjectStorageAccessDeniedError):
            await storage.get(key, expected_sha256=SHA, max_bytes=len(BODY))
        with pytest.raises(ObjectStorageAccessDeniedError):
            await storage.head(key)
        with pytest.raises(ObjectStorageAccessDeniedError):
            await storage.delete(key)
        with pytest.raises(ObjectStorageAccessDeniedError):
            await storage.put(f"{RUN}/cross-bucket", b"x", content_type="text/plain")

    assert await _present(writer_a, object_in_a)
    assert await _present(writer_b, object_in_b)
    assert not await _present(writer_a, f"{RUN}/cross-bucket")
    assert not await _present(writer_b, f"{RUN}/cross-bucket")


# --- anonymous access, on the real object URL ----------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE"])
async def test_anonymous_requests_for_a_real_object_are_denied(method, writer_a, object_in_a):
    url = f"{CONFIG['ENDPOINT']}/{CONFIG['BUCKET_A']}/{object_in_a}"

    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.request(method, url, content=b"anonymous" if method == "PUT" else None)

    assert response.status_code == 403
    if method != "HEAD":  # a HEAD response has no body to carry the code
        assert "<Code>AccessDenied</Code>" in response.text
    assert BODY.decode() not in response.text
    assert await writer_a.get(object_in_a, expected_sha256=SHA, max_bytes=len(BODY)) == BODY


# --- typed failures -------------------------------------------------------------------------


async def test_a_missing_object_is_not_found_rather_than_denied(reader_a, writer_a):
    for storage in (reader_a, writer_a):
        with pytest.raises(ObjectNotFoundError):
            await storage.head(f"{RUN}/does-not-exist")
        with pytest.raises(ObjectNotFoundError):
            await storage.get(f"{RUN}/does-not-exist", expected_sha256=SHA, max_bytes=10)


async def test_wrong_credentials_are_denied(object_in_a):
    impostor = _storage("READER_A", "BUCKET_A", secret_access_key="not-the-right-secret-0000000000")

    with pytest.raises(ObjectStorageAccessDeniedError):
        await impostor.head(object_in_a)


async def test_an_unreachable_service_is_a_retryable_unavailable_error():
    unreachable = _storage("READER_A", "BUCKET_A", endpoint_url="http://127.0.0.1:9", connect_timeout_seconds=1)

    with pytest.raises(ObjectStorageUnavailableError) as caught:
        await unreachable.head(f"{RUN}/anything")

    assert caught.value.is_retryable is True


async def test_failures_against_the_real_service_log_no_secret_key_or_bytes(reader_a, object_in_a, caplog):
    _, secret = _credentials("READER_A")

    with caplog.at_level(logging.DEBUG), pytest.raises(ObjectStorageAccessDeniedError):
        await reader_a.put(f"{RUN}/denied-put", BODY, content_type="application/pdf")

    for leaked in (secret, f"{RUN}/denied-put", BODY.decode()):
        assert leaked not in caplog.text


# --- nothing left behind --------------------------------------------------------------------


def test_zz_no_test_objects_remain():
    # Runs last (file order): every fixture and test above removed what it
    # stored, including after failures.
    for identity, bucket in (("WRITER_A", "BUCKET_A"), ("WRITER_B", "BUCKET_B")):
        access, secret = _credentials(identity)
        s3 = boto3.session.Session().client(
            "s3",
            endpoint_url=CONFIG["ENDPOINT"],
            region_name=CONFIG["REGION"] or "us-east-1",
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 1}),
        )
        left = s3.list_objects_v2(Bucket=CONFIG[bucket], Prefix=RUN + "/").get("Contents", [])
        assert left == [], f"{len(left)} test object(s) remain in {bucket}"
