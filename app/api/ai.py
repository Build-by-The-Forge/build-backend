"""Backend AI endpoints (design B.5): the only client path to AI-service.

Each request is authenticated, resolved to a tenant and an active membership
(x-tenant-slug), checked for one permission, bounded and rate limited per
user, then forwarded to AI-service as a signed call for that user. Nothing is
persisted. The body cannot name a tenant or user: identity comes only from
the verified session and membership.
"""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.application.identity.throttle import AuthThrottle
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.exceptions import AppError
from app.core.tenant_context import TenantContext
from app.domain.ai.assistant import AIActor, AIAssistantError, AIAssistantGateway
from app.infrastructure.ai.assistant_gateway import HttpAIAssistantGateway

router = APIRouter(prefix="/ai", tags=["ai"])
throttle = build_container().get(AuthThrottle)

MAX_MESSAGE_CHARS = 4000
MAX_QUESTION_COUNT = 50
_CORRELATION_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class AIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(AIRequest):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ExplainRequest(AIRequest):
    subject: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class GenerateQuestionsRequest(AIRequest):
    topic: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    count: int = Field(default=5, ge=1, le=MAX_QUESTION_COUNT)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question_type: Literal["mcq", "true_false"] = "mcq"


def get_ai_assistant_gateway() -> AIAssistantGateway:
    return HttpAIAssistantGateway()


def _actor(request: Request, context: TenantContext, permission: Permission) -> AIActor:
    request_id = getattr(request.state, "request_id", None)
    correlation_id = request_id if isinstance(request_id, str) and _CORRELATION_ID_RE.fullmatch(request_id) else str(uuid.uuid4())
    return AIActor(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        membership_id=context.membership_id,
        role=context.role,
        permission=permission.value,
        correlation_id=correlation_id,
    )


def _envelope(request: Request, data: dict[str, object]) -> JSONResponse:
    return JSONResponse(
        content={
            "success": True,
            "data": data,
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        }
    )


def _failed(exc: AIAssistantError) -> AppError:
    # The client learns only that the AI step failed, not why.
    if exc.unavailable:
        return AppError("ai service unavailable", status_code=503)
    return AppError("ai service error", status_code=502)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.AI_USE)),
    gateway: AIAssistantGateway = Depends(get_ai_assistant_gateway),
) -> JSONResponse:
    await throttle.ai_request(context.user_id)
    try:
        result = await gateway.chat(_actor(request, context, Permission.AI_USE), body.message)
    except AIAssistantError as exc:
        raise _failed(exc) from exc
    return _envelope(request, {"answer": result.answer, "context": result.context})


@router.post("/explain")
async def explain(
    body: ExplainRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.AI_USE)),
    gateway: AIAssistantGateway = Depends(get_ai_assistant_gateway),
) -> JSONResponse:
    await throttle.ai_request(context.user_id)
    try:
        result = await gateway.explain(_actor(request, context, Permission.AI_USE), body.subject)
    except AIAssistantError as exc:
        raise _failed(exc) from exc
    return _envelope(request, {"explanation": result.explanation})


@router.post("/generate-questions")
async def generate_questions(
    body: GenerateQuestionsRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.AI_QUESTIONS_GENERATE)),
    gateway: AIAssistantGateway = Depends(get_ai_assistant_gateway),
) -> JSONResponse:
    await throttle.ai_question_generation(context.user_id)
    try:
        result = await gateway.generate_questions(
            _actor(request, context, Permission.AI_QUESTIONS_GENERATE),
            body.topic,
            body.count,
            body.difficulty,
            body.question_type,
        )
    except AIAssistantError as exc:
        raise _failed(exc) from exc
    # Proposals for the lecturer to review; nothing is saved (M5 ruling R2).
    return _envelope(
        request,
        {"questions": [q.to_dict() for q in result.questions], "discarded": result.discarded},
    )
