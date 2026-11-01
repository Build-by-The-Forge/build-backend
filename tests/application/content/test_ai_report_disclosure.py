"""A signed report isn't display text. Internal URLs and secret-like diagnostics
are injected through every field the AI service controls."""

from app.domain.content.ai_report import (
    DEFAULT_FAILURE_MESSAGE,
    UNKNOWN_FAILURE_CODE,
    public_failure_message,
    safe_attempt_record,
    safe_error_code,
    safe_evidence,
)

LEAK = "http://ai-service.internal:8000/v1 password=hunter2 Traceback sk-provider-key"


def test_a_failure_message_comes_only_from_its_code():
    assert public_failure_message("AI_TASK_LOST") == "Processing stopped unexpectedly."
    assert public_failure_message(LEAK) == DEFAULT_FAILURE_MESSAGE
    assert public_failure_message(None) == DEFAULT_FAILURE_MESSAGE


def test_a_code_that_is_not_a_code_is_replaced():
    assert safe_error_code("OCR_PAGE_FAILED") == "OCR_PAGE_FAILED"
    assert safe_error_code(LEAK) == UNKNOWN_FAILURE_CODE
    assert safe_error_code("lowercase") == UNKNOWN_FAILURE_CODE
    assert safe_error_code("A" * 65) == UNKNOWN_FAILURE_CODE
    assert safe_error_code(None) == UNKNOWN_FAILURE_CODE


def test_evidence_keeps_what_the_pipeline_reports():
    report = {
        "characters": 120,
        "method": "ocr",
        "index": "document_chunks",
        "embedding_model": "all-MiniLM-L6-v2",
        "chunk_summary": {
            "fetch": {"verified": True, "sha256": "a" * 64, "size_bytes": 10, "mime_type": "application/pdf"},
            "extraction": {"pages": 2, "seconds": 0.5},
        },
    }
    assert safe_evidence(report) == report


def test_evidence_drops_unknown_fields_and_free_text_at_every_depth():
    report = {
        "provider_error": LEAK,
        "method": LEAK,
        "index": "http://internal",
        "embedding_model": "/opt/models/secret",
        "mime_type": LEAK,
        "sha256": LEAK,
        "characters": LEAK,
        "chunk_summary": {"fetch": {"storage_uri": LEAK, "verified": LEAK, "size_bytes": 3}, "note": LEAK},
    }
    kept = safe_evidence(report)
    assert kept == {"chunk_summary": {"fetch": {"size_bytes": 3}}}
    assert "hunter2" not in str(kept)


def test_an_old_attempt_record_is_clean_on_the_way_out():
    stored = {
        "attempt": 1,
        "error_code": "AI_SERVICE_TRANSPORT_ERROR",
        "error_message": LEAK,
        "error_details": {"url": LEAK},
    }
    clean = safe_attempt_record(stored)
    assert "hunter2" not in str(clean)
    assert clean["attempt"] == 1
    assert clean["error_details"] == {}
