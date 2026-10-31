from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

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
assessment_attempts_finalized_total = Counter(
    "build_backend_assessment_attempts_finalized_total",
    "Expired attempts the worker finalized with no client involved",
    registry=registry,
)
learning_memory_enabled = Gauge(
    "build_backend_learning_memory_enabled",
    "1 when learning memory is enabled in this process, 0 when the gate keeps it off",
    registry=registry,
)
learning_memory_refusals_total = Counter(
    "build_backend_learning_memory_refusals_total",
    "Learning-memory reads and writes the production gate stopped before sending",
    ["operation"],
    registry=registry,
)

content_upload_orphaned_objects_total = Counter(
    "build_backend_content_upload_orphaned_objects_total",
    "Uploaded objects left without an asset row because compensation failed",
    ["reason"],
    registry=registry,
)
content_jobs_dispatched_total = Counter(
    "build_backend_content_jobs_dispatched_total",
    "Ingestion attempts accepted by the AI service",
    registry=registry,
)
content_dispatch_failures_total = Counter(
    "build_backend_content_dispatch_failures_total",
    "Definite ingestion dispatch failures",
    ["error_code"],
    registry=registry,
)
content_uncertain_dispatches_total = Counter(
    "build_backend_content_uncertain_dispatches_total",
    "Ingestion dispatches whose remote outcome is uncertain",
    registry=registry,
)
content_retries_scheduled_total = Counter(
    "build_backend_content_retries_scheduled_total",
    "Retryable ingestion failures scheduled for another attempt",
    registry=registry,
)
content_terminal_failures_total = Counter(
    "build_backend_content_terminal_failures_total",
    "Ingestion jobs failed permanently",
    ["error_code"],
    registry=registry,
)
content_recoveries_total = Counter(
    "build_backend_content_recoveries_total",
    "Recoverer decisions for overdue ingestion jobs",
    ["outcome"],
    registry=registry,
)
content_in_flight_cap_hits_total = Counter(
    "build_backend_content_in_flight_cap_hits_total",
    "AI tasks failed after reaching the maximum in-flight duration",
    registry=registry,
)
content_orphan_objects_deleted_total = Counter(
    "build_backend_content_orphan_objects_deleted_total",
    "Stored objects deleted by the orphan sweeper",
    ["reason"],
    registry=registry,
)
content_orphan_objects_kept_total = Counter(
    "build_backend_content_orphan_objects_kept_total",
    "Stored objects kept by the orphan sweeper",
    ["reason"],
    registry=registry,
)
content_jobs_due = Gauge(
    "build_backend_content_jobs_due",
    "Queued ingestion jobs currently eligible for dispatch",
    registry=registry,
)
content_oldest_due_job_age_seconds = Gauge(
    "build_backend_content_oldest_due_job_age_seconds",
    "Age of the oldest queued ingestion job eligible for dispatch",
    registry=registry,
)


def metrics_payload() -> bytes:
    return generate_latest(registry)
