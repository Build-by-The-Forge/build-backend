import logging

import structlog

from app.core.redaction import RedactingFilter, redact_event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            redact_event_dict,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=logging.INFO)
    # Handler-level filter: applies to records from every logger, including
    # third-party ones, that reach the root handlers.
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
