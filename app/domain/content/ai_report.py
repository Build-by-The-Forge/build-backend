"""What the AI service's reports may leave behind on a job.

A signed report proves who sent it, not that its text is fit to show. So nothing
free-form is kept: a failure's message comes from its code, and evidence passes an
allowlist of the fields the pipeline reports. The full report goes to the log.
"""

import math
import re
from typing import Any

UNKNOWN_FAILURE_CODE = "AI_PROCESSING_FAILED"
DEFAULT_FAILURE_MESSAGE = "The document could not be processed."

_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")

_UNAVAILABLE = "The processing service is temporarily unavailable."
_STORAGE = "The stored document could not be read."
_DISPATCH = "The document could not be sent for processing."

_FAILURE_MESSAGES = {
    "AI_TASK_LOST": "Processing stopped unexpectedly.",
    "AI_TASK_TIMEOUT": "Processing took too long.",
    "AI_SERVICE_NOT_CONFIGURED": _UNAVAILABLE,
    "AI_SERVICE_TRANSPORT_ERROR": _UNAVAILABLE,
    "AI_SERVICE_UNAVAILABLE": _UNAVAILABLE,
    "AI_SERVICE_BAD_RESPONSE": _DISPATCH,
    "AI_IDEMPOTENCY_CONFLICT": _DISPATCH,
    "AI_DISPATCH_FAILED": _DISPATCH,
    "AI_DISPATCH_UNCERTAIN": _DISPATCH,
    "JOB_TENANT_MISSING": _DISPATCH,
    "INGESTION_PIPELINE_UNAVAILABLE": _UNAVAILABLE,
    "UNREGISTERED_HANDLER": _UNAVAILABLE,
    "EMBEDDING_FAILED": "The document's text could not be indexed.",
    "INDEX_WRITE_FAILED": "The document's text could not be indexed.",
    "STALE_INDEX_WRITE": "A newer attempt replaced this one.",
    "ASSET_FETCH_TIMEOUT": _STORAGE,
    "ASSET_NOT_FOUND": _STORAGE,
    "ASSET_REFERENCE_REJECTED": _STORAGE,
    "ASSET_OBJECT_MISSING": _STORAGE,
    "ASSET_OBJECT_MISMATCH": "The stored document doesn't match what was uploaded.",
    "ASSET_INTEGRITY_MISMATCH": "The stored document doesn't match what was uploaded.",
    "OBJECT_STORAGE_ACCESS_DENIED": _STORAGE,
    "OBJECT_STORAGE_FAILURE": _STORAGE,
    "OBJECT_STORAGE_MISCONFIGURED": _STORAGE,
    "OBJECT_STORAGE_NOT_CONFIGURED": _STORAGE,
    "OBJECT_STORAGE_UNAVAILABLE": _STORAGE,
    "ASSET_TOO_LARGE": "The document is too large to process.",
    "ASSET_TOO_MANY_PAGES": "The document has too many pages to process.",
    "ASSET_TYPE_MISMATCH": "The document's type doesn't match its contents.",
    "EXTRACTION_EMPTY": "No text could be found in the document.",
    "EXTRACTION_TIMEOUT": "Reading the document took too long.",
    "IMAGE_UNREADABLE": "An image in the document could not be read.",
    "OCR_PAGE_FAILED": "A page of the document could not be read.",
    "PDF_UNREADABLE": "The document could not be read.",
}

_MEASURES = frozenset(
    {
        "attempt",
        "characters",
        "chunks",
        "count",
        "dimension",
        "empty_pages",
        "indexed_chunks",
        "low_confidence_pages",
        "mean_ocr_confidence",
        "native_pages",
        "ocr_pages",
        "pages",
        "pages_covered",
        "seconds",
        "size_bytes",
        "uncertain_dispatch_attempt",
        "uncertain_dispatch_count",
    }
)
_FLAGS = frozenset({"verified"})
_SECTIONS = frozenset({"chunk_summary", "chunking", "embedding", "extraction", "fetch", "indexing"})
_STRINGS = {
    "embedding_model": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"),
    "index": re.compile(r"[a-z_]{1,64}"),
    "method": re.compile(r"[a-z_]{1,64}"),
    "mime_type": re.compile(r"[a-z]+/[a-z0-9.+-]{1,100}"),
    "sha256": re.compile(r"[0-9a-f]{64}"),
}


def safe_error_code(code: str | None) -> str:
    return code if code is not None and _CODE.fullmatch(code) else UNKNOWN_FAILURE_CODE


def public_failure_message(code: str | None) -> str:
    return _FAILURE_MESSAGES.get(code or "", DEFAULT_FAILURE_MESSAGE)


def _safe_measure(value: Any) -> bool:
    # bool is an int in Python, and JSON can carry NaN and Infinity into a float.
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def safe_evidence(report: dict[str, Any]) -> dict[str, Any]:
    """Only the fields the pipeline is known to report, each in its expected form."""
    kept: dict[str, Any] = {}
    for key, value in report.items():
        if key in _SECTIONS and isinstance(value, dict):
            kept[key] = safe_evidence(value)
        elif key in _FLAGS and isinstance(value, bool):
            kept[key] = value
        elif key in _MEASURES and _safe_measure(value):
            kept[key] = value
        elif key in _STRINGS and isinstance(value, str) and _STRINGS[key].fullmatch(value):
            kept[key] = value
    return kept


_RECORD_FIELDS = ("attempt", "external_task_id", "stage_at_failure", "is_retryable", "failed_at")


def safe_attempt_record(record: dict[str, Any]) -> dict[str, Any]:
    """An attempt's history entry for display, including rows stored before this filter."""
    return {
        **{key: record[key] for key in _RECORD_FIELDS if key in record},
        "error_code": safe_error_code(record.get("error_code")),
        "error_message": public_failure_message(record.get("error_code")),
        "error_details": safe_evidence(record.get("error_details") or {}),
    }
