"""Signed delivery of scope assignments to the AI service (M3-D PR 5).

POST /v1/ingest/scope-assignments with a system context for the document's
tenant. The AI service applies an assignment only if its version is higher
than the one it holds, and returns the version it holds either way, so a
replay or a late older assignment is still answered. Only an answer naming
the document and a version at least the one sent counts as delivery.
"""

from __future__ import annotations

import json
import time

import httpx

from app.core.config import settings
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import Direction, ServiceKeys, sign_request

PATH = "/v1/ingest/scope-assignments"


class ScopeDeliveryError(Exception):
    """Not delivered; the row stays pending. ``code`` is safe to store."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HttpScopeAssignmentGateway:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
        keys: ServiceKeys | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ai_service_url).rstrip("/")
        self._timeout = float(timeout_seconds or settings.ai_service_timeout_seconds)
        self._client = client
        self._keys_override = keys

    def _keys(self) -> ServiceKeys:
        if self._keys_override is not None:
            return self._keys_override
        if not settings.backend_to_ai_secret:
            raise ScopeDeliveryError("AI_SERVICE_NOT_CONFIGURED")
        return ServiceKeys(current=settings.backend_to_ai_secret)

    async def assign(self, *, tenant_id: str, asset_id: str, scope: str, version: int, correlation_id: str) -> int:
        """The version the AI service holds after this assignment."""
        body = json.dumps({"asset_id": asset_id, "scope": scope, "version": version}).encode()
        url = httpx.URL(f"{self._base_url}{PATH}")
        headers = sign_request(
            direction=Direction.BACKEND_TO_AI,
            keys=self._keys(),
            method="POST",
            target=url.raw_path.decode("ascii"),
            body=body,
            context=ServiceContext.for_system(tenant_id=tenant_id, correlation_id=correlation_id),
            timestamp=int(time.time()),
        )
        headers["Content-Type"] = "application/json"
        client = self._client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        try:
            response = await client.post(url, content=body, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ScopeDeliveryError("AI_SERVICE_UNREACHABLE") from exc
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code == 409:
            # Another tenant holds the asset: a contract break, never retried away.
            raise ScopeDeliveryError("ASSET_HELD_BY_ANOTHER_TENANT")
        if response.status_code != 200:
            raise ScopeDeliveryError(f"AI_SERVICE_HTTP_{response.status_code}")
        try:
            data = response.json()
            stored_asset, stored_version = data["asset_id"], data["version"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ScopeDeliveryError("AI_SERVICE_BAD_RESPONSE") from exc
        if stored_asset != asset_id or isinstance(stored_version, bool) or not isinstance(stored_version, int):
            raise ScopeDeliveryError("AI_SERVICE_BAD_RESPONSE")
        if stored_version < version:
            # It holds an older version than the one just sent: not delivered.
            raise ScopeDeliveryError("AI_SERVICE_STALE_VERSION")
        return stored_version
