from prometheus_client import CollectorRegistry, Counter, generate_latest

registry = CollectorRegistry(auto_describe=True)
requests_total = Counter(
    "build_backend_requests_total",
    "Total number of requests processed by the backend",
    registry=registry,
)


def metrics_payload() -> bytes:
    return generate_latest(registry)
