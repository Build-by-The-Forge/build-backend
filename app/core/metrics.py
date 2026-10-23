from prometheus_client import CollectorRegistry, Counter, generate_latest

registry = CollectorRegistry(auto_describe=True)
requests_total = Counter(
    "build_backend_requests_total",
    "Total number of requests processed by the backend",
    registry=registry,
)
errors_total = Counter(
    "build_backend_errors_total",
    "Total number of failed requests handled by the backend",
    ["error_type"],
    registry=registry,
)

# An uploaded object whose compensating delete failed after its asset row
# could not be committed (P3-1 PR 2, docs/p3-1-pr2-upload-design.md, section
# 6). Each one is an orphan until P3-6's reconciliation removes it.
content_upload_orphaned_objects_total = Counter(
    "build_backend_content_upload_orphaned_objects_total",
    "Uploaded objects left without an asset row because compensation failed",
    ["reason"],
    registry=registry,
)


def metrics_payload() -> bytes:
    return generate_latest(registry)
