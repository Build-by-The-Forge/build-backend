from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import time
from urllib.parse import quote
from typing import Any

import httpx

from app.core.config import settings
from app.domain.content.asset import ContentAsset
from app.domain.content.gateway import (
    AIServiceDispatchResult,
    AIServiceIngestionGateway,
    AIServiceStatusResult,
    IngestionDispatchActor,
)
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    Direction,
    ServiceKeys,
    sign_request,
)

_CORRELATION_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def _correlation_id(job: ContentIngestionJob) -> str:
    """The job's correlation id when it fits the signed-context format,
    otherwise the job id."""
    candidate = job.correlation_id
    if candidate and _CORRELATION_ID_RE.fullmatch(candidate):
        return candidate
    return job.id


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


class HttpAIServiceIngestionGateway(AIServiceIngestionGateway):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
        keys: ServiceKeys | None = None,
    ) -> None:
        self._keys_override = keys
        self._base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._timeout_seconds = (
            timeout_seconds or settings.ai_service_timeout_seconds
        )
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=float(self._timeout_seconds))

    def _keys(self) -> ServiceKeys:
        if self._keys_override is not None:
            return self._keys_override
        if not settings.backend_to_ai_secret:
            raise AIServiceGatewayError(
                message="BACKEND_TO_AI_SECRET is not configured",
                error_code="AI_SERVICE_NOT_CONFIGURED",
                is_retryable=True,
            )
        return ServiceKeys(current=settings.backend_to_ai_secret)

    async def dispatch_ingestion_job(
        self,
        job: ContentIngestionJob,
        asset: ContentAsset,
        source: ContentSource,
        actor: IngestionDispatchActor,
    ) -> AIServiceDispatchResult:
        """Signed dispatch (BUILD Service Signature v1, design B.2).

        The body names no tenant and no callback URL; the tenant reaches
        AI-service only through the signed user context.
        """
        keys = self._keys()
        mime_val = (
            asset.mime_type.value
            if hasattr(asset.mime_type, "value")
            else str(asset.mime_type)
        )
        correlation_id = _correlation_id(job)
        body = json.dumps(
            {
                "job_id": job.id,
                "asset_id": asset.id,
                "source_id": source.id,
                "run_number": job.run_number,
                "attempt_count": job.attempt_count,
                "idempotency_key": f"{job.id}-r{job.run_number}-a{job.attempt_count}",
                "mime_type": mime_val,
                "content_sha256": asset.content_sha256,
                "storage_uri": asset.storage_uri,
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        context = ServiceContext.for_user(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            membership_id=actor.membership_id,
            role=actor.role,
            permissions=[actor.permission],
            correlation_id=correlation_id,
        )

        url = httpx.URL(f"{self._base_url}/v1/ingest/dispatch")
        headers = sign_request(
            direction=Direction.BACKEND_TO_AI,
            keys=keys,
            method="POST",
            target=url.raw_path.decode("ascii"),  # path and query exactly as sent
            body=body,
            context=context,
            timestamp=int(time.time()),
        )
        headers["Content-Type"] = "application/json"

        should_close = self._client is None
        client = await self._get_client()

        try:
            response = await client.post(url, content=body, headers=headers)
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
            task_id = data.get("external_task_id") if isinstance(data, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise AIServiceGatewayError(
                    message="AI Service accepted the dispatch without an external_task_id",
                    error_code="AI_SERVICE_BAD_RESPONSE",
                    is_retryable=True,
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
        self, external_task_id: str, tenant_id: str, correlation_id: str
    ) -> AIServiceStatusResult:
        """Signed GET /v1/ingest/tasks/{id} with a system context naming the
        job's tenant (design B.3); AI-service answers only for that tenant."""
        keys = self._keys()
        url = httpx.URL(
            f"{self._base_url}/v1/ingest/tasks/{quote(external_task_id, safe='')}"
        )
        headers = sign_request(
            direction=Direction.BACKEND_TO_AI,
            keys=keys,
            method="GET",
            target=url.raw_path.decode("ascii"),
            body=b"",
            context=ServiceContext.for_system(
                tenant_id=tenant_id, correlation_id=correlation_id
            ),
            timestamp=int(time.time()),
        )

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
            try:
                data = response.json()
                return AIServiceStatusResult(
                    external_task_id=str(data["external_task_id"]),
                    job_id=str(data["job_id"]),
                    run_number=int(data["run_number"]),
                    attempt_count=int(data["attempt_count"]),
                    state=str(data["state"]),
                    events=[dict(e) for e in data["events"]],
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise AIServiceGatewayError(
                    message="AI Service returned an unreadable task status",
                    error_code="AI_SERVICE_BAD_RESPONSE",
                    is_retryable=True,
                ) from exc

        if response.status_code == 404:
            raise AIServiceGatewayError(
                message="AI Service has no such task for this tenant",
                error_code="AI_TASK_NOT_FOUND",
                is_retryable=False,
                details={"status_code": 404},
            )
        if response.status_code in (401, 403):
            raise AIServiceGatewayError(
                message=f"AI Service authentication failed (HTTP {response.status_code})",
                error_code="AI_SERVICE_AUTH_ERROR",
                is_retryable=False,
                details={"status_code": response.status_code},
            )
        raise AIServiceGatewayError(
            message=f"Failed to fetch task status from AI Service (HTTP {response.status_code})",
            error_code="AI_SERVICE_POLL_FAILED",
            is_retryable=response.status_code >= 500,
            details={"status_code": response.status_code},
        )
