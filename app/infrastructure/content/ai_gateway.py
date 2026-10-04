from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any

import httpx

from app.core.config import settings
from app.domain.content.asset import ContentAsset
from app.domain.content.gateway import (
    AIServiceDispatchResult,
    AIServiceIngestionGateway,
    AIServiceStatusResult,
)
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource


class AIServiceGatewayError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "AI_SERVICE_ERROR",
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.is_retryable = is_retryable
        self.details = details or {}


def compute_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(
    payload_bytes: bytes, signature_header: str | None, secret: str
) -> bool:
    if not signature_header or not secret:
        return False

    parts = signature_header.strip().split("=")
    if len(parts) == 2 and parts[0] == "sha256":
        provided_digest = parts[1].strip()
    else:
        provided_digest = signature_header.strip()

    expected_digest = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided_digest, expected_digest)


class HttpAIServiceIngestionGateway(AIServiceIngestionGateway):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._api_key = api_key or settings.ai_service_api_key
        self._timeout_seconds = (
            timeout_seconds or settings.ai_service_timeout_seconds
        )
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=float(self._timeout_seconds))

    async def dispatch_ingestion_job(
        self,
        job: ContentIngestionJob,
        asset: ContentAsset,
        source: ContentSource,
        callback_url: str,
    ) -> AIServiceDispatchResult:
        idempotency_key = f"{job.id}-r{job.run_number}-a{job.attempt_count}"
        correlation_id = job.correlation_id or job.id
        tenant_id = job.tenant_id or "platform"

        url = f"{self._base_url}/v1/ingest/dispatch"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json",
        }
        mime_val = (
            asset.mime_type.value
            if hasattr(asset.mime_type, "value")
            else str(asset.mime_type)
        )
        payload = {
            "job_id": job.id,
            "run_number": job.run_number,
            "attempt_count": job.attempt_count,
            "asset_id": asset.id,
            "source_id": source.id,
            "tenant_id": job.tenant_id,
            "file_name": asset.file_name,
            "mime_type": mime_val,
            "file_size_bytes": asset.file_size_bytes,
            "content_sha256": asset.content_sha256,
            "storage_uri": asset.storage_uri,
            "callback_url": callback_url,
            "correlation_id": correlation_id,
        }

        should_close = self._client is None
        client = await self._get_client()

        try:
            response = await client.post(url, json=payload, headers=headers)
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise AIServiceGatewayError(
                message=f"Timeout communicating with AI Service at {url}: {exc}",
                error_code="AI_SERVICE_TIMEOUT",
                is_retryable=True,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise AIServiceGatewayError(
                message=f"Network error connecting to AI Service at {url}: {exc}",
                error_code="AI_SERVICE_CONNECTION_ERROR",
                is_retryable=True,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code in (200, 201, 202):
            data = response.json()
            task_id = (
                data.get("task_id")
                or data.get("external_task_id")
                or f"aitask-{job.id}"
            )
            return AIServiceDispatchResult(
                external_task_id=task_id,
                accepted_at=datetime.now(timezone.utc),
                status=data.get("status", "accepted"),
                raw_response=data,
            )

        if response.status_code in (502, 503, 504):
            raise AIServiceGatewayError(
                message=f"AI Service transient error (HTTP {response.status_code}): {response.text}",
                error_code="AI_SERVICE_UNAVAILABLE",
                is_retryable=True,
                details={"status_code": response.status_code, "body": response.text},
            )

        if response.status_code in (401, 403):
            raise AIServiceGatewayError(
                message=f"AI Service authentication failed (HTTP {response.status_code})",
                error_code="AI_SERVICE_AUTH_ERROR",
                is_retryable=False,
                details={"status_code": response.status_code},
            )

        raise AIServiceGatewayError(
            message=f"AI Service rejected dispatch request (HTTP {response.status_code}): {response.text}",
            error_code="AI_SERVICE_REJECTED",
            is_retryable=False,
            details={"status_code": response.status_code, "body": response.text},
        )

    async def fetch_job_status(
        self, external_task_id: str
    ) -> AIServiceStatusResult:
        url = f"{self._base_url}/v1/ingest/tasks/{external_task_id}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        should_close = self._client is None
        client = await self._get_client()
        try:
            response = await client.get(url, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIServiceGatewayError(
                message=f"Error fetching task status from AI Service: {exc}",
                error_code="AI_SERVICE_POLL_ERROR",
                is_retryable=True,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 200:
            data = response.json()
            return AIServiceStatusResult(
                external_task_id=external_task_id,
                status=data.get("status", "unknown"),
                stage=data.get("stage"),
                metrics=data.get("metrics", {}),
                error_code=data.get("error_code"),
                error_message=data.get("error_message"),
                is_retryable=data.get("is_retryable", False),
            )

        raise AIServiceGatewayError(
            message=f"Failed to fetch task status from AI Service (HTTP {response.status_code})",
            error_code="AI_SERVICE_POLL_FAILED",
            is_retryable=response.status_code >= 500,
        )

    async def cancel_ingestion_job(self, external_task_id: str) -> bool:
        url = f"{self._base_url}/v1/ingest/tasks/{external_task_id}/cancel"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        should_close = self._client is None
        client = await self._get_client()
        try:
            response = await client.post(url, headers=headers)
            return response.status_code in (200, 204)
        except Exception:
            return False
        finally:
            if should_close:
                await client.aclose()
