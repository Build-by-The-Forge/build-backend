"""object-storage-init (deploy/compose.m3.yml): prepare and prove the
document bucket before the backend starts. Runs once, in the backend image,
with the app's own S3ObjectStorage adapter.

1. The admin identity creates the bucket, retrying until a real write
   succeeds (readiness, not just a live process).
2. The backend identity can put, get with SHA-256 verification, and delete.
3. The AI identity can read and inspect, but cannot write or delete.
4. An anonymous request for a real object is denied.

Exits non-zero on any failure. Prints no credentials, keys or bytes.
"""

import asyncio
import os
import sys
import time
import uuid

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.domain.content.storage import ObjectStorageAccessDeniedError
from app.infrastructure.content.s3_object_storage import S3ObjectStorage

ENDPOINT = os.environ["OBJECT_STORAGE_ENDPOINT_URL"]
BUCKET = os.environ["OBJECT_STORAGE_BUCKET"]


def _storage(prefix: str) -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket=BUCKET,
        endpoint_url=ENDPOINT,
        access_key_id=os.environ[f"{prefix}_ACCESS_KEY"],
        secret_access_key=os.environ[f"{prefix}_SECRET_KEY"],
        addressing_style="path",
        max_attempts=1,
    )


def create_bucket() -> None:
    admin = boto3.session.Session().client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id=os.environ["OBJECT_STORAGE_ADMIN_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OBJECT_STORAGE_ADMIN_SECRET_KEY"],
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 1},
            connect_timeout=3,
            read_timeout=10,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    deadline = time.monotonic() + 90
    while True:
        try:
            admin.create_bucket(Bucket=BUCKET)
            return
        except ClientError as exc:
            code = exc.response["Error"].get("Code")
            if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                return
            error = code
        except BotoCoreError as exc:
            error = type(exc).__name__
        if time.monotonic() > deadline:
            sys.exit(f"object-storage-init: bucket not created within 90 s ({error})")
        time.sleep(1)


async def prove() -> None:
    backend = _storage("OBJECT_STORAGE_BACKEND")
    ai = _storage("OBJECT_STORAGE_AI")
    key = f"setup/init-probe-{uuid.uuid4().hex}"
    body = b"object-storage-init probe"
    stored = await backend.put(key, body, content_type="text/plain")
    try:
        if await backend.get(key, expected_sha256=stored.sha256, max_bytes=len(body)) != body:
            sys.exit("object-storage-init: the backend identity read back different bytes")
        if await ai.get(key, expected_sha256=stored.sha256, max_bytes=len(body)) != body:
            sys.exit("object-storage-init: the AI identity read back different bytes")
        try:
            await ai.put(f"{key}-ai", b"x", content_type="text/plain")
            sys.exit("object-storage-init: the AI identity could write; it must be read-only")
        except ObjectStorageAccessDeniedError:
            pass
        try:
            await ai.delete(key)
            sys.exit("object-storage-init: the AI identity could delete; it must be read-only")
        except ObjectStorageAccessDeniedError:
            pass
        async with httpx.AsyncClient(timeout=5) as client:
            anonymous = await client.get(f"{ENDPOINT}/{BUCKET}/{key}")
        if anonymous.status_code != 403:
            sys.exit(f"object-storage-init: anonymous object access was not denied (HTTP {anonymous.status_code})")
    finally:
        await backend.delete(key)


def main() -> None:
    create_bucket()
    asyncio.run(prove())
    print(f"object-storage-init: bucket {BUCKET} ready; backend read/write, AI read-only, anonymous denied")


if __name__ == "__main__":
    main()
