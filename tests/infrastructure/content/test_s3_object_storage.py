"""S3ObjectStorage without a network: botocore's Stubber checks every request
against the S3 API model and returns scripted responses. Real-service
behaviour is proven in test_s3_object_storage_seaweedfs.py."""

import base64
import hashlib
import io
import logging
from datetime import datetime, timezone

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError, ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.core.config import Settings
from app.domain.content.storage import (
    InvalidObjectKeyError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorageAccessDeniedError,
    ObjectStorageConfigurationError,
    ObjectStorageError,
    ObjectStorageUnavailableError,
    ObjectTooLargeError,
)
from app.infrastructure.content.s3_object_storage import S3ObjectStorage, validate_object_key

BUCKET = "build-documents"
KEY = "tenants/t-1/assets/a-1/" + "0" * 64
BODY = b"%PDF-1.7 a small document with 6H2O + = ? %\n"
SHA = hashlib.sha256(BODY).hexdigest()
SECRET = "unit-test-secret-key-that-must-never-be-logged"


@pytest.fixture
def stubbed():
    client = boto3.session.Session().client(
        "s3",
        endpoint_url="http://storage.invalid:8333",
        region_name="us-east-1",
        aws_access_key_id="unit-test-access-key",
        aws_secret_access_key=SECRET,
        config=Config(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    with Stubber(client) as stubber:
        yield S3ObjectStorage(bucket=BUCKET, client=client), stubber, client
        stubber.assert_no_pending_responses()


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


# --- put ------------------------------------------------------------------------------------


async def test_put_computes_sha256_and_sends_it_as_metadata_and_checksum(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response(
        "put_object",
        {"ETag": '"md5-not-a-checksum"'},
        expected_params={
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": BODY,
            "ContentLength": len(BODY),
            "ContentType": "application/pdf",
            "Metadata": {"sha256": SHA},
            "ChecksumSHA256": base64.b64encode(bytes.fromhex(SHA)).decode(),
        },
    )

    stored = await storage.put(KEY, BODY, content_type="application/pdf")

    assert (stored.key, stored.size_bytes, stored.sha256, stored.content_type) == (KEY, len(BODY), SHA, "application/pdf")


async def test_put_streams_a_seekable_file_from_its_start(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response(
        "put_object",
        {"ETag": '"x"'},
        expected_params={
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": ANY,
            "ContentLength": len(BODY),
            "ContentType": "application/pdf",
            "Metadata": {"sha256": SHA},
            "ChecksumSHA256": ANY,
        },
    )
    file = io.BytesIO(BODY)

    stored = await storage.put(KEY, file, content_type="application/pdf")

    assert stored.sha256 == SHA
    assert file.tell() == 0  # rewound after hashing, for the upload


async def test_put_refuses_bytes_that_do_not_match_the_expected_sha256_without_writing(stubbed):
    storage, _, _ = stubbed  # no response queued: any request would fail the test

    with pytest.raises(ObjectIntegrityError) as caught:
        await storage.put(KEY, BODY, content_type="application/pdf", expected_sha256="f" * 64)

    assert caught.value.error_code == "OBJECT_INTEGRITY_MISMATCH"
    assert caught.value.is_retryable is False


async def test_put_accepts_a_matching_expected_sha256_in_any_case(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("put_object", {"ETag": '"x"'})

    stored = await storage.put(KEY, BODY, content_type="application/pdf", expected_sha256=SHA.upper())

    assert stored.sha256 == SHA


async def test_a_body_corrupted_in_transit_is_a_retryable_integrity_error(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_client_error("put_object", service_error_code="BadDigest", http_status_code=400)

    with pytest.raises(ObjectIntegrityError) as caught:
        await storage.put(KEY, BODY, content_type="application/pdf")

    assert (caught.value.error_code, caught.value.is_retryable) == ("OBJECT_TRANSFER_CORRUPTED", True)


# --- get ------------------------------------------------------------------------------------


async def test_get_returns_the_bytes_when_their_sha256_matches(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response(
        "get_object",
        {"Body": _body(BODY), "ContentLength": len(BODY)},
        expected_params={"Bucket": BUCKET, "Key": KEY},
    )

    assert await storage.get(KEY, expected_sha256=SHA, max_bytes=1024) == BODY


async def test_get_refuses_stored_bytes_that_do_not_match_the_expected_sha256(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("get_object", {"Body": _body(b"tampered"), "ContentLength": 8})

    with pytest.raises(ObjectIntegrityError) as caught:
        await storage.get(KEY, expected_sha256=SHA, max_bytes=1024)

    assert (caught.value.error_code, caught.value.is_retryable) == ("OBJECT_INTEGRITY_MISMATCH", False)


async def test_get_refuses_an_object_whose_declared_size_exceeds_the_limit(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("get_object", {"Body": _body(BODY), "ContentLength": len(BODY)})

    with pytest.raises(ObjectTooLargeError):
        await storage.get(KEY, expected_sha256=SHA, max_bytes=len(BODY) - 1)


async def test_get_stops_reading_once_the_limit_is_exceeded_without_a_declared_size(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("get_object", {"Body": _body(BODY)})

    with pytest.raises(ObjectTooLargeError):
        await storage.get(KEY, expected_sha256=SHA, max_bytes=8)


async def test_get_requires_a_well_formed_expected_sha256(stubbed):
    storage, _, _ = stubbed

    with pytest.raises(ValueError):
        await storage.get(KEY, expected_sha256="not-a-digest", max_bytes=1024)


# --- head and delete ------------------------------------------------------------------------


async def test_head_reports_size_type_and_the_stored_sha256_as_information(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response(
        "head_object",
        {"ContentLength": len(BODY), "ContentType": "application/pdf", "Metadata": {"sha256": SHA}},
        expected_params={"Bucket": BUCKET, "Key": KEY},
    )

    info = await storage.head(KEY)

    assert (info.size_bytes, info.content_type, info.sha256) == (len(BODY), "application/pdf", SHA)


async def test_head_ignores_a_malformed_sha256_in_metadata(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("head_object", {"ContentLength": 1, "Metadata": {"sha256": "nonsense"}})

    assert (await storage.head(KEY)).sha256 is None


async def test_delete_deletes_the_key(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_response("delete_object", {}, expected_params={"Bucket": BUCKET, "Key": KEY})

    await storage.delete(KEY)


async def test_list_page_uses_continuation_token_and_returns_modified_times(stubbed):
    storage, stubber, _ = stubbed
    modified = datetime(2026, 10, 1, tzinfo=timezone.utc)
    stubber.add_response(
        "list_objects_v2",
        {
            "IsTruncated": True,
            "NextContinuationToken": "next-page",
            "Contents": [{"Key": KEY, "LastModified": modified}],
        },
        expected_params={"Bucket": BUCKET, "Prefix": "tenants/", "MaxKeys": 1000},
    )
    stubber.add_response(
        "list_objects_v2",
        {"IsTruncated": False, "Contents": []},
        expected_params={
            "Bucket": BUCKET,
            "Prefix": "tenants/",
            "MaxKeys": 1000,
            "ContinuationToken": "next-page",
        },
    )

    first = await storage.list_page(prefix="tenants/")
    second = await storage.list_page(prefix="tenants/", continuation_token=first.continuation_token)

    assert first.objects[0].key == KEY
    assert first.objects[0].last_modified == modified
    assert first.continuation_token == "next-page"
    assert second.objects == ()
    assert second.continuation_token is None


@pytest.mark.parametrize("max_keys", [0, 1001])
async def test_list_page_rejects_invalid_page_size_without_requesting_storage(stubbed, max_keys):
    storage, _, _ = stubbed
    with pytest.raises(ValueError, match="max_keys"):
        await storage.list_page(prefix="tenants/", max_keys=max_keys)


# --- error mapping --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "status", "expected_type", "expected_code", "retryable"),
    [
        ("NoSuchKey", 404, ObjectNotFoundError, "OBJECT_NOT_FOUND", False),
        ("404", 404, ObjectNotFoundError, "OBJECT_NOT_FOUND", False),
        ("AccessDenied", 403, ObjectStorageAccessDeniedError, "OBJECT_STORAGE_ACCESS_DENIED", False),
        ("SignatureDoesNotMatch", 403, ObjectStorageAccessDeniedError, "OBJECT_STORAGE_ACCESS_DENIED", False),
        ("InvalidAccessKeyId", 403, ObjectStorageAccessDeniedError, "OBJECT_STORAGE_ACCESS_DENIED", False),
        ("NoSuchBucket", 404, ObjectStorageConfigurationError, "OBJECT_STORAGE_NOT_CONFIGURED", False),
        ("SlowDown", 503, ObjectStorageUnavailableError, "OBJECT_STORAGE_UNAVAILABLE", True),
        ("InternalError", 500, ObjectStorageUnavailableError, "OBJECT_STORAGE_UNAVAILABLE", True),
        ("SomethingNew", 502, ObjectStorageUnavailableError, "OBJECT_STORAGE_UNAVAILABLE", True),
        ("SomethingNew", 400, ObjectStorageError, "OBJECT_STORAGE_ERROR", False),
    ],
)
async def test_provider_errors_become_typed_errors(stubbed, code, status, expected_type, expected_code, retryable):
    storage, stubber, _ = stubbed
    stubber.add_client_error("get_object", service_error_code=code, http_status_code=status)

    with pytest.raises(ObjectStorageError) as caught:
        await storage.get(KEY, expected_sha256=SHA, max_bytes=1024)

    assert type(caught.value) is expected_type
    assert (caught.value.error_code, caught.value.is_retryable) == (expected_code, retryable)


async def test_an_unknown_error_is_never_reported_as_not_found(stubbed):
    storage, stubber, _ = stubbed
    stubber.add_client_error("head_object", service_error_code="SomethingNew", http_status_code=400)

    with pytest.raises(ObjectStorageError) as caught:
        await storage.head(KEY)

    assert not isinstance(caught.value, ObjectNotFoundError)


@pytest.mark.parametrize(
    "exception",
    [
        EndpointConnectionError(endpoint_url="http://storage.invalid:8333"),
        ReadTimeoutError(endpoint_url="http://storage.invalid:8333"),
    ],
)
async def test_an_unreachable_store_is_a_retryable_unavailable_error(stubbed, monkeypatch, exception):
    storage, _, client = stubbed

    def fail(**_kwargs):
        raise exception

    monkeypatch.setattr(client, "head_object", fail)

    with pytest.raises(ObjectStorageUnavailableError) as caught:
        await storage.head(KEY)

    assert caught.value.is_retryable is True


# --- keys, configuration and logs -----------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["", "/absolute", "a//b", "a/./b", "a/../b", "..", "back\\slash", "tab\there", "x" * 1025],
)
async def test_unsafe_keys_are_refused_before_any_request(stubbed, key):
    storage, _, _ = stubbed

    with pytest.raises(InvalidObjectKeyError):
        await storage.head(key)


def test_a_server_generated_key_is_accepted():
    assert validate_object_key(KEY) == KEY


def test_storage_without_a_bucket_or_credentials_is_a_configuration_error():
    with pytest.raises(ObjectStorageConfigurationError):
        S3ObjectStorage.from_settings(Settings(object_storage_bucket=""))
    with pytest.raises(ObjectStorageConfigurationError):
        S3ObjectStorage.from_settings(Settings(object_storage_bucket=BUCKET))


def test_the_secret_never_appears_in_settings_or_adapter_representations():
    config = Settings(
        object_storage_bucket=BUCKET,
        object_storage_access_key_id="unit-test-access-key",
        object_storage_secret_access_key=SECRET,
    )

    assert SECRET not in repr(config)
    assert SECRET not in str(config.model_dump())
    assert SECRET not in repr(S3ObjectStorage.from_settings(config))


def test_the_aws_sdk_never_logs_request_parameters():
    # botocore logs request parameters, object bytes included, at DEBUG.
    for name in ("boto3", "botocore", "s3transfer", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


async def test_failure_logs_carry_no_secret_key_or_object_bytes(stubbed, caplog):
    storage, stubber, _ = stubbed
    stubber.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)

    with caplog.at_level(logging.DEBUG), pytest.raises(ObjectStorageAccessDeniedError):
        await storage.put(KEY, BODY, content_type="application/pdf")

    logged = caplog.text
    assert "object storage put failed: OBJECT_STORAGE_ACCESS_DENIED" in logged
    for leaked in (SECRET, KEY, BODY.decode()):
        assert leaked not in logged
