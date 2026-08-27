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


def metrics_payload() -> bytes:
    return generate_latest(registry)
