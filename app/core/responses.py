from typing import Any

from fastapi.responses import JSONResponse


class ApiResponse(JSONResponse):
    def __init__(
        self,
        data: Any = None,
        *,
        success: bool = True,
        meta: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        payload = {
            "success": success,
            "data": data or {},
            "meta": meta or {},
        }
        if request_id is not None:
            payload["request_id"] = request_id
        super().__init__(content=payload)
