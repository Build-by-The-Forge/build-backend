import logging

import structlog

from app.core.redaction import RedactingFilter, redact_event_dict

# The AWS SDK logs request parameters, which can include object bytes, at
# DEBUG. These loggers stay at WARNING whatever the root level (Phase 3, P3-1).
_AWS_SDK_LOGGERS = ("boto3", "botocore", "s3transfer", "urllib3")


def quiet_aws_sdk_loggers() -> None:
    for name in _AWS_SDK_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_logging() -> None:
    quiet_aws_sdk_loggers()
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
