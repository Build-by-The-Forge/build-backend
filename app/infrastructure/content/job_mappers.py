from __future__ import annotations

from app.domain.content.enums import IngestionStatus
from app.domain.content.job import ContentIngestionJob
from app.infrastructure.db.models.content import ContentIngestionJobModel


def content_job_to_model(job: ContentIngestionJob, model: ContentIngestionJobModel | None = None) -> ContentIngestionJobModel:
    if model is None:
        model = ContentIngestionJobModel(id=job.id)

    model.asset_id = job.asset_id
    model.source_id = job.source_id
    model.tenant_id = job.tenant_id
    model.run_number = job.run_number
    model.status = job.status.value
    model.current_stage = job.current_stage
    model.attempt_count = job.attempt_count
    model.max_attempts = job.max_attempts
    model.error_code = job.error_code
    model.error_message = job.error_message
    model.error_details = dict(job.error_details)
    model.is_retryable = job.is_retryable
    model.next_retry_at = job.next_retry_at
    model.started_at = job.started_at
    model.completed_at = job.completed_at
    model.metrics = dict(job.metrics)
    model.attempt_history = list(job.attempt_history)
    model.correlation_id = job.correlation_id
    model.external_task_id = job.external_task_id
    model.last_dispatched_at = job.last_dispatched_at
    model.last_callback_at = job.last_callback_at
    model.dispatch_claim_token = job.dispatch_claim_token
    model.dispatch_claim_expires_at = job.dispatch_claim_expires_at
    model.created_by = job.created_by
    model.created_at = job.created_at
    model.updated_at = job.updated_at
    return model


def content_job_model_to_domain(model: ContentIngestionJobModel) -> ContentIngestionJob:
    return ContentIngestionJob(
        id=model.id,
        asset_id=model.asset_id,
        source_id=model.source_id,
        tenant_id=model.tenant_id,
        run_number=model.run_number,
        status=IngestionStatus(model.status),
        current_stage=model.current_stage,
        attempt_count=model.attempt_count,
        max_attempts=model.max_attempts,
        error_code=model.error_code,
        error_message=model.error_message,
        error_details=dict(model.error_details) if model.error_details else {},
        is_retryable=model.is_retryable,
        next_retry_at=model.next_retry_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        metrics=dict(model.metrics) if model.metrics else {},
        attempt_history=list(model.attempt_history) if model.attempt_history else [],
        correlation_id=model.correlation_id,
        external_task_id=model.external_task_id,
        last_dispatched_at=model.last_dispatched_at,
        last_callback_at=model.last_callback_at,
        dispatch_claim_token=model.dispatch_claim_token,
        dispatch_claim_expires_at=model.dispatch_claim_expires_at,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
