# Phase 1 Inspection Report: Assessment Core Slice 1 (Question + QuestionOption)

**Date:** 2026-08-22  
**Version:** v0.6.0 Catalogue Baseline  
**Status:** Ready for Architecture Review  

---

## Executive Summary

This report documents the existing patterns and conventions in the build-backend codebase, specifically focused on the patterns that Question and QuestionOption aggregates must follow for Slice 1 of Assessment Core. The backend implements:

- **Domain-Driven Design** with clean layering (domain → application → infrastructure → api)
- **Multi-tenant isolation** enforced at every layer
- **Event-driven architecture** with in-process event bus
- **Repository pattern** with tenant-scoped queries
- **Async SQLAlchemy 2.0** with Alembic migrations
- **FastAPI** with permission-based authorization

All inspected files are referenced in this report. **Question and QuestionOption must follow these patterns exactly** — no new abstractions.

---

## 1. Domain Model Patterns

### 1.1 Aggregate Structure

**Files:**
- [app/domain/catalogue/course.py](app/domain/catalogue/course.py)
- [app/domain/catalogue/topic.py](app/domain/catalogue/topic.py)
- [app/domain/catalogue/learning_outcome.py](app/domain/catalogue/learning_outcome.py)

**Pattern:**
```python
@dataclass
class AggregateRoot:
    id: IdValueObject
    # ... domain fields using value objects
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(cls, ...) -> AggregateRoot:
        instance = cls(id=IdValueObject("") or IdValueObject(""), ...)
        instance._events.append(DomainEvent(event_type="...", payload={...}))
        return instance

    def archive(self) -> None:
        if self.status == Status.ARCHIVED:
            raise AlreadyArchivedError("...")
        self.status = Status.ARCHIVED
        self.touch()
        self._events.append(DomainEvent(...))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
```

**Key Observations:**
1. Aggregates are `@dataclass` with `slots=True` (Course uses default, consider consistent slots)
2. ID fields use empty-string initialization → auto-generates UUID in `__post_init__`
3. `created_at`/`updated_at` use UTC timezone
4. Events stored in `_events` list, cleared by `pull_events()`
5. Domain invariants enforced in domain methods (e.g., archive-twice raises)
6. No tenant_id in domain models (purely domain concern)
7. Child entities (Topic, LearningOutcome, ReferenceMaterial) are NOT aggregate roots — they're owned by their parent

### 1.2 Entity vs Aggregate Boundary

**Key Decision:** Only Course is an aggregate root. Topic and LearningOutcome are child entities with lifecycle tied to Course.

**Pattern in Course:**
```python
topics: list["Topic"] = field(default_factory=list, repr=False)

def add_topic(self, topic: "Topic") -> None:
    if topic.course_id != self.id:
        raise ValueError("course_id mismatch")
    self.topics.append(topic)
    self.touch()
    self._events.append(DomainEvent(...))
```

**Implication for Question:**
- Question **must be an aggregate root** (not owned by Topic)
- QuestionOption **is a child entity**, not an aggregate root
- QuestionOption is always accessed through Question
- Events are emitted from Question, not from QuestionOption

### 1.3 Value Objects

**Files:**
- [app/domain/catalogue/value_objects.py](app/domain/catalogue/value_objects.py) (175+ lines)

**Pattern:**
```python
@dataclass(frozen=True, slots=True)
class SpecificValueObject:
    value: str | int

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            object.__setattr__(self, "value", str(uuid4()))
        # ... validation logic raises ValueError if invalid

    def __str__(self) -> str:
        return self.value
```

**Catalog Value Objects Already Defined:**
- CourseId, TopicId, LearningOutcomeId, ReferenceMaterialId (UUID strings)
- CourseCode, CourseTitle, CourseSlug (with validation)
- CourseCreditUnits, CourseLevel, CourseSemester (int enums)
- CourseStatus, TopicStatus, LearningOutcomeStatus (str Enums)
- TopicSequence, LearningOutcomeSequence, TopicLevel

**Required for Question:**
- QuestionId (UUID string, auto-generated)
- QuestionType (enum: MCQ only for Slice 1)
- Difficulty (enum: easy, medium, hard, etc.)
- Marks (positive int, 1-100 range)
- Prompt (string, min length validation)
- Explanation (string)

**For QuestionOption:**
- QuestionOptionId (UUID string)
- OptionText (string, min/max validation)
- DisplayOrder (int, 1-N per question)
- IsCorrect (bool, no value object needed)

**Invariant:** Value objects validate in `__post_init__`, raising ValueError for invalid inputs.

### 1.4 Status Enums

**Pattern (from CourseStatus, TopicStatus, LearningOutcomeStatus):**
```python
class CourseStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

# Corresponds to database default "active" and supports transitions
```

**For Question:**
```python
class QuestionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
```

**No preliminary states like PENDING_REVIEW** — Question goes DRAFT → PUBLISHED directly (for Slice 1).

### 1.5 Error Handling

**Pattern (from catalogue/errors.py):**
```python
class CourseAlreadyArchivedError(Exception):
    pass

class TopicAlreadyArchivedError(Exception):
    pass
```

**Required for Question:**
- QuestionAlreadyArchivedError
- InvalidMCQError (invalid option count, no correct answer, etc.)
- InvalidLearningOutcomeError (belongs to different topic/tenant)

---

## 2. Application Layer Patterns (Commands & Handlers)

### 2.1 Command Structure

**Files:**
- [app/application/catalogue/commands.py](app/application/catalogue/commands.py)
- [app/application/catalogue/handlers.py](app/application/catalogue/handlers.py)

**Pattern:**
```python
@dataclass(slots=True)
class CreateCourseCommand:
    # All inputs as data, no logic
    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    description: str | None = None
    tenant_id: str | None = None  # Comes from TenantContext, not client

@dataclass(slots=True)
class UpdateTopicCommand:
    topic_id: str
    title: str | None = None
    description: str | None = None
    tenant_id: str | None = None

@dataclass(slots=True)
class ArchiveCommand:  # Not used yet, but pattern would be:
    resource_id: str
    tenant_id: str | None = None
```

**Key Invariant:** 
- Command includes `tenant_id`, but it's always passed from TenantContext
- Client cannot inject tenant_id (API layer validates this with `extra="forbid"`)
- tenant_id is None-by-default, resolved at API boundary

**For Question Commands:**
```python
@dataclass(slots=True)
class CreateQuestionCommand:
    topic_id: str
    question_type: str  # "mcq"
    prompt: str
    explanation: str
    difficulty: str  # "easy", "medium", "hard"
    marks: int
    learning_outcome_id: str | None = None
    options: list[dict[str, object]] | None = None  # API transforms to domain
    tenant_id: str | None = None

@dataclass(slots=True)
class UpdateQuestionCommand:
    question_id: str
    prompt: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    marks: int | None = None
    tenant_id: str | None = None

@dataclass(slots=True)
class ArchiveQuestionCommand:
    question_id: str
    tenant_id: str | None = None
```

### 2.2 Handler Structure

**Pattern:**
```python
class CreateCourseHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateCourseCommand) -> Course:
        # Construct value objects (validates)
        course = Course.create(
            department_id=DepartmentId(command.department_id),
            code=CourseCode(command.code),
            # ...
        )
        # Persist through repository
        return await self.repository.save(course, tenant_id=command.tenant_id)
```

**Key Observations:**
1. Handler receives repository (injected)
2. Handler constructs value objects (raises if validation fails)
3. Handler calls domain aggregate's factory method
4. Handler persists via repository (tenant_id passed explicitly)
5. No Unit of Work visible in simple handlers; UoW used at service/API layer

**For Question:**
```python
class CreateQuestionHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateQuestionCommand) -> Question:
        # Validate catalogue relationships (topic/outcome exist, same tenant)
        topic = await self._get_topic(command.topic_id, command.tenant_id)
        learning_outcome = None
        if command.learning_outcome_id:
            learning_outcome = await self._get_learning_outcome(
                command.learning_outcome_id, command.topic_id, command.tenant_id
            )

        # Construct and persist
        question = Question.create(
            topic_id=TopicId(command.topic_id),
            question_type=QuestionType(command.question_type),
            prompt=Prompt(command.prompt),
            # ...
            learning_outcome_id=learning_outcome.id if learning_outcome else None,
        )
        return await self.repository.save(question, tenant_id=command.tenant_id)
```

### 2.3 Catalog Relationship Validation

**Pattern from CreateTopicHandler and CreateLearningOutcomeHandler:**

Topics are saved through Course repository (because Topic is child of Course):
```python
async def handle(self, command: CreateTopicCommand) -> Topic | None:
    # Get parent aggregate
    course = await self.repository.get_by_id(
        command.course_id, tenant_id=command.tenant_id
    )
    if course is None:
        return None
    
    # Create child
    topic = Topic.create(...)
    
    # Add to parent
    course.add_topic(topic)
    
    # Persist parent (cascades child)
    await self.repository.save(course, tenant_id=command.tenant_id)
    
    return topic
```

**For Question (different pattern — Question is its own aggregate):**
```python
async def handle(self, command: CreateQuestionCommand) -> Question:
    # Validate catalogue references exist and belong to tenant
    topic = await self.catalogue_repo.get_topic(
        command.topic_id, tenant_id=command.tenant_id
    )
    if not topic:
        raise ValidationError("Topic not found or not in current tenant")
    
    if command.learning_outcome_id:
        outcome = await self.catalogue_repo.get_learning_outcome(
            command.learning_outcome_id, tenant_id=command.tenant_id
        )
        if not outcome or outcome.topic_id != topic.id:
            raise ValidationError("LearningOutcome not in topic")
    
    # Create Question aggregate
    question = Question.create(...)
    
    # Persist Question directly (not through Course)
    return await self.repository.save(question, tenant_id=command.tenant_id)
```

---

## 3. Repository & Persistence Patterns

### 3.1 Repository Protocol

**File:** [app/domain/repositories/course.py](app/domain/repositories/course.py)

**Pattern:**
```python
class CourseRepository(Protocol):
    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        """Insert or update course, enforcing tenant ownership."""

    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        """Retrieve by ID, scoped to tenant if provided."""

    async def list_all(self, tenant_id: str | None = None) -> list[Course]:
        """List all courses for tenant."""

    async def list_by_department(self, department_id: str, tenant_id: str | None = None) -> list[Course]:
        """List by department, scoped to tenant."""

    async def get_by_topic_id(self, topic_id: str, tenant_id: str | None = None) -> Course | None:
        """Find course that owns this topic."""

    async def get_by_learning_outcome_id(self, learning_outcome_id: str, tenant_id: str | None = None) -> Course | None:
        """Find course that owns this learning outcome."""
```

**Key Rules:**
1. All repository methods accept optional `tenant_id` parameter
2. If `tenant_id` is provided, query is scoped to that tenant at **database level**
3. Returns domain aggregates, not ORM models
4. Never returns global results when tenant is expected

**For QuestionRepository Protocol:**
```python
class QuestionRepository(Protocol):
    async def save(self, question: Question, tenant_id: str | None = None) -> Question:
        """Save question, enforcing tenant ownership."""

    async def get_by_id(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        """Retrieve question by ID, scoped to tenant."""

    async def list_by_topic(self, topic_id: str, tenant_id: str | None = None) -> list[Question]:
        """List questions in topic, scoped to tenant."""

    async def list_by_learning_outcome(self, learning_outcome_id: str, tenant_id: str | None = None) -> list[Question]:
        """List questions for a learning outcome, scoped to tenant."""

    async def archive(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        """Archive a question, scoped to tenant."""
```

### 3.2 SQLAlchemy Repository Implementation

**File:** [app/infrastructure/catalogue/repositories.py](app/infrastructure/catalogue/repositories.py)

**Pattern:**
```python
class SqlAlchemyCourseRepository(CourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        statement = select(CourseModel).where(CourseModel.id == course_id)
        
        # CRITICAL: Always add tenant filter if tenant_id provided
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        
        # CRITICAL: Eager load all relationships before mapping
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        
        result = await self._session.scalars(statement)
        model = result.first()
        
        # Map ORM model to domain aggregate
        return course_to_domain(model) if model is not None else None

    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        statement = select(CourseModel).where(CourseModel.id == course.id.value)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        # ... eager load relationships
        
        result = await self._session.scalars(statement)
        model = result.first()
        
        if model is None:
            # NEW: Create ORM model from domain
            model = course_to_model(course)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            # UPDATE: Map domain to existing ORM model
            course_to_model(course, model=model)
            if tenant_id is not None:
                model.tenant_id = tenant_id
        
        await self._session.flush()  # Note: no commit here, UoW handles that
        return course
```

**Key Observations:**
1. Eager load all related entities with `selectinload()` before mapping
2. Always add `tenant_id` filter even for updates (security)
3. `flush()` not `commit()` — transaction managed by caller
4. Mapper functions (`course_to_domain`, `course_to_model`) handle conversions

### 3.3 Mapper Pattern

**File:** [app/infrastructure/catalogue/mappers.py](app/infrastructure/catalogue/mappers.py)

**Pattern:**
```python
def course_to_domain(model: CourseModel | None) -> Course | None:
    if model is None:
        return None
    
    # Recursively map children
    topics = [topic_to_domain(t) for t in model.topics]
    references = [reference_material_to_domain(r) for r in model.reference_materials]
    
    return Course(
        id=CourseId(model.id),
        department_id=DepartmentId(model.department_id),
        code=CourseCode(model.code),
        title=CourseTitle(model.title),
        # ... all fields
        status=CourseStatus(model.status),
        topics=topics,
        references=references,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )

def course_to_model(
    course: Course,
    model: CourseModel | None = None
) -> CourseModel:
    """Update existing model or create new from domain."""
    if model is None:
        model = CourseModel()
    
    model.id = course.id.value
    model.department_id = course.department_id.value
    model.code = course.code.value
    model.title = course.title.value
    # ... all fields
    model.status = course.status.value
    # Note: Topics/References NOT updated here (they're managed through parent)
    model.updated_at = course.updated_at
    
    return model
```

**Key Observations:**
1. Bidirectional mappers (to_domain, to_model)
2. Recursive mapping for nested entities
3. Value objects extracted with `.value`
4. Enum status converted via `CourseStatus(str_value)`
5. Child entities mapped recursively (for Course) or embedded (for QuestionOption)

---

## 4. Unit of Work & Transaction Management

### 4.1 Async UnitOfWork Base Class

**File:** [app/infrastructure/unit_of_work.py](app/infrastructure/unit_of_work.py)

**Pattern:**
```python
class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
        await self.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def close(self) -> None:
        await self.session.close()
```

### 4.2 Bounded Context UnitOfWork

**Files:**
- [app/infrastructure/catalogue/unit_of_work.py](app/infrastructure/catalogue/unit_of_work.py)
- [app/infrastructure/identity/unit_of_work.py](app/infrastructure/identity/unit_of_work.py)

**Pattern:**
```python
class CourseUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.courses = SqlAlchemyCourseRepository(session)

@asynccontextmanager
async def catalogue_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[CourseUnitOfWork]:
    async with CourseUnitOfWork(session) as uow:
        yield uow
```

**Key Observations:**
1. UnitOfWork extends base with specific repositories
2. Always async context manager
3. Single session shared across all repositories
4. Auto-commit on exit (unless exception)

**For Assessment Core:**
```python
class AssessmentUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.questions = SqlAlchemyQuestionRepository(session)
        # Later: self.question_banks, self.assessments, etc.

@asynccontextmanager
async def assessment_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[AssessmentUnitOfWork]:
    async with AssessmentUnitOfWork(session) as uow:
        yield uow
```

---

## 5. API Layer Patterns

### 5.1 Route Structure

**File:** [app/api/catalogue/courses.py](app/api/catalogue/courses.py)

**Pattern:**
```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/catalogue/courses", tags=["catalogue"])

@router.get("/", status_code=status.HTTP_200_OK)
async def list_courses(
    request: Request,
    department_id: str | None = None,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_READ)
    ),
) -> JSONResponse:
    try:
        courses = await service.list_courses(
            department_id=department_id,
            tenant_id=context.tenant_id
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [
                {
                    "id": course.id.value,
                    "code": course.code.value,
                    # ... all fields as dict
                }
                for course in courses
            ],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_course(
    request: Request,
    payload: CreateCourseRequest,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_CREATE)
    ),
) -> JSONResponse:
    try:
        course = await service.create_course(
            tenant_id=context.tenant_id,  # CRITICAL: from context, not payload
            department_id=payload.department_id,
            # ... other fields
        )
    except ValueError as exc:
        # Domain validation error
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "data": {}, "meta": {"error": str(exc)}, ...}
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, ...}
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": CourseResponse(...).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )

@router.post("/{course_id}/archive", status_code=status.HTTP_200_OK)
async def archive_course(
    course_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CATALOGUE_ARCHIVE)
    ),
) -> JSONResponse:
    # Implementation
```

**Key Patterns:**
1. All endpoints depend on `require_permission(Permission.*)` — enforces authorization
2. TenantContext injected via dependency, containing user_id, tenant_id, role
3. tenant_id always passed from context, never from payload
4. Payloads validated with Pydantic schemas (`extra="forbid"`)
5. Response envelope: `{"success": bool, "data": {...}, "meta": {...}, "request_id": "..."}`
6. All responses return JSONResponse with explicit status code
7. Exception handling catches domain errors and returns appropriate HTTP status
8. request_id from `request.state.request_id` (injected by middleware)

### 5.2 Request/Response Schemas

**File:** [app/api/catalogue/schemas.py](app/api/catalogue/schemas.py)

**Pattern:**
```python
from pydantic import BaseModel, ConfigDict, Field

class CreateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # CRITICAL: reject unknown fields

    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    description: str | None = None
    # Note: tenant_id NOT in schema

class CourseResponse(BaseModel):
    id: str
    department_id: str
    code: str
    title: str
    slug: str
    credit_units: int
    level: int
    semester: int
    status: str
    description: str | None = None

class UpdateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
```

**For Question:**
```python
class CreateQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    question_type: str  # "mcq"
    prompt: str
    explanation: str
    difficulty: str  # "easy", "medium", "hard"
    marks: int = Field(gt=0, le=100)
    learning_outcome_id: str | None = None
    options: list[QuestionOptionRequest]  # Nested

class QuestionOptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    display_order: int
    is_correct: bool

class QuestionOptionResponse(BaseModel):
    id: str
    text: str
    display_order: int
    # Note: is_correct NOT included for student-facing responses

class QuestionResponse(BaseModel):
    id: str
    topic_id: str
    question_type: str
    prompt: str
    explanation: str
    difficulty: str
    marks: int
    status: str
    learning_outcome_id: str | None = None
    options: list[QuestionOptionResponse]
    created_at: datetime
    updated_at: datetime

class QuestionAuthoringResponse(BaseModel):
    # Same as above but includes is_correct in options
    pass  # Reuse QuestionOptionResponse, but need variant
```

---

## 6. Authorization & Permission System

### 6.1 Permission Definitions

**File:** [app/core/authorization.py](app/core/authorization.py)

**Current Permissions:**
```python
class Permission(StrEnum):
    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_CREATE = "catalogue.create"
    CATALOGUE_UPDATE = "catalogue.update"
    CATALOGUE_ARCHIVE = "catalogue.archive"
    CATALOGUE_PUBLISH = "catalogue.publish"
```

**Role-Permission Matrix:**
```python
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "student": frozenset({Permission.CATALOGUE_READ}),
    "lecturer": frozenset({
        Permission.CATALOGUE_READ,
        Permission.CATALOGUE_CREATE,
        Permission.CATALOGUE_UPDATE,
    }),
    "hod": frozenset({
        Permission.CATALOGUE_READ,
        Permission.CATALOGUE_CREATE,
        Permission.CATALOGUE_UPDATE,
    }),
    "faculty_admin": frozenset({
        Permission.CATALOGUE_READ,
        Permission.CATALOGUE_CREATE,
        Permission.CATALOGUE_UPDATE,
        Permission.CATALOGUE_ARCHIVE,
        Permission.CATALOGUE_PUBLISH,
    }),
    "admin": frozenset(Permission),  # All permissions
    "owner": frozenset(Permission),  # All permissions
}
```

**For Assessment Core (Slice 1):**

Add new permissions:
```python
class Permission(StrEnum):
    # Existing catalogue permissions
    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_CREATE = "catalogue.create"
    CATALOGUE_UPDATE = "catalogue.update"
    CATALOGUE_ARCHIVE = "catalogue.archive"
    CATALOGUE_PUBLISH = "catalogue.publish"
    
    # Assessment permissions
    ASSESSMENT_READ = "assessment.read"
    ASSESSMENT_QUESTION_CREATE = "assessment.question.create"
    ASSESSMENT_QUESTION_UPDATE = "assessment.question.update"
    ASSESSMENT_QUESTION_ARCHIVE = "assessment.question.archive"
```

**Update role matrix:**
```python
"student": frozenset({
    Permission.CATALOGUE_READ,
    Permission.ASSESSMENT_READ,  # Can view published questions
}),
"lecturer": frozenset({
    # ... catalogue permissions
    Permission.ASSESSMENT_READ,
    Permission.ASSESSMENT_QUESTION_CREATE,
    Permission.ASSESSMENT_QUESTION_UPDATE,
}),
"faculty_admin": frozenset({
    # ... all catalogue permissions
    Permission.ASSESSMENT_READ,
    Permission.ASSESSMENT_QUESTION_CREATE,
    Permission.ASSESSMENT_QUESTION_UPDATE,
    Permission.ASSESSMENT_QUESTION_ARCHIVE,
}),
```

### 6.2 TenantContext

**File:** [app/core/tenant_context.py](app/core/tenant_context.py)

**Pattern:**
```python
@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: str
    tenant_id: str
    membership_id: str
    role: str
```

**Populated by:** [app/core/dependencies.py](app/core/dependencies.py) `get_current_tenant_context()`

**Rules:**
1. Derived from `X-Tenant-Slug` header (never from body)
2. Verified through tenant lookup and membership check
3. Passed to all service/repository calls
4. Immutable (frozen dataclass)

---

## 7. Database & Persistence

### 7.1 ORM Model Structure

**File:** [app/infrastructure/db/models/catalogue.py](app/infrastructure/db/models/catalogue.py)

**Pattern for Course:**
```python
class CourseModel(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    topics: Mapped[list["TopicModel"]] = relationship(
        "TopicModel",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TopicModel.sequence",
    )
    reference_materials: Mapped[list["ReferenceMaterialModel"]] = relationship(
        "ReferenceMaterialModel",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        UniqueConstraint("tenant_id", "slug", name="uq_courses_tenant_slug"),
        Index("ix_courses_department_id", "department_id"),
        Index("ix_courses_tenant_id", "tenant_id"),
    )
```

**Pattern for Topic (child entity):**
```python
class TopicModel(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    course: Mapped["CourseModel"] = relationship(
        "CourseModel",
        back_populates="topics",
    )
    learning_outcomes: Mapped[list["LearningOutcomeModel"]] = relationship(
        "LearningOutcomeModel",
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LearningOutcomeModel.sequence",
    )

    __table_args__ = (
        UniqueConstraint("course_id", "sequence", name="uq_topic_course_sequence"),
        Index("ix_topics_course_id", "course_id"),
    )
```

**Key Observations:**
1. All models extend Base (from app.db.base)
2. tenant_id is always present and foreign-keyed to tenants
3. status field is string with server_default
4. created_at/updated_at with UTC timezone
5. Relationships use cascade="all, delete-orphan" for child entities
6. Unique constraints combine tenant_id + natural key
7. Indexes on foreign keys and tenant_id

**For Question:**
```python
class QuestionModel(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    learning_outcome_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("learning_outcomes.id", ondelete="SET NULL"), nullable=True
    )
    question_type: Mapped[str] = mapped_column(String(20), nullable=False, default="mcq")
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    topic: Mapped["TopicModel"] = relationship("TopicModel")
    learning_outcome: Mapped["LearningOutcomeModel | None"] = relationship(
        "LearningOutcomeModel"
    )
    options: Mapped[list["QuestionOptionModel"]] = relationship(
        "QuestionOptionModel",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionOptionModel.display_order",
    )

    __table_args__ = (
        Index("ix_questions_tenant_id", "tenant_id"),
        Index("ix_questions_topic_id", "topic_id"),
        Index("ix_questions_learning_outcome_id", "learning_outcome_id"),
    )

class QuestionOptionModel(Base):
    __tablename__ = "question_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    question: Mapped["QuestionModel"] = relationship(
        "QuestionModel",
        back_populates="options",
    )

    __table_args__ = (
        UniqueConstraint("question_id", "display_order", name="uq_option_question_order"),
        Index("ix_question_options_question_id", "question_id"),
    )
```

### 7.2 Alembic Migration Pattern

**File:** [alembic/versions/0005_add_catalogue_schema.py](alembic/versions/0005_add_catalogue_schema.py)

**Pattern:**
```python
"""0005 add catalogue schema - courses, curriculum_versions, topics, learning_outcomes

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02
"""

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create courses table
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=False),
        # ... other columns
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_courses_tenant_slug"),
    )
    op.create_index("ix_courses_tenant_id", "courses", ["tenant_id"])
    op.create_index("ix_courses_department_id", "courses", ["department_id"])

    # Create topics table
    op.create_table(
        "topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        # ... other columns
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    # ... indexes

def downgrade() -> None:
    op.drop_table("topics")
    op.drop_table("courses")
```

**For Assessment Core Slice 1:**

Naming convention: `0006_add_assessment_schema_questions`
```python
"""0006 add assessment schema - questions, question_options

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22
"""

revision = "0006"
down_revision = "0005"

def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("topic_id", sa.String(36), nullable=False),
        sa.Column("learning_outcome_id", sa.String(36), nullable=True),
        sa.Column("question_type", sa.String(20), nullable=False, server_default="mcq"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(20), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["learning_outcome_id"], ["learning_outcomes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_questions_tenant_id", "questions", ["tenant_id"])
    op.create_index("ix_questions_topic_id", "questions", ["topic_id"])

    op.create_table(
        "question_options",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question_id", sa.String(36), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", "display_order", name="uq_option_question_order"),
    )
    op.create_index("ix_question_options_question_id", "question_options", ["question_id"])
```

---

## 8. Event System

### 8.1 Event Bus

**File:** [app/events/event_bus.py](app/events/event_bus.py)

**Pattern:**
```python
class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event_name: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if payload is None:
            payload = kwargs
        event = DomainEvent(event_type=event_name, payload=payload)
        for handler in self._subscribers.get(event_name, []):
            handler(event)

    def publish_all(self, events: list[DomainEvent]) -> None:
        for event in events:
            for handler in self._subscribers.get(event.event_type, []):
                handler(event)
```

**Key Observations:**
1. In-process event bus (not distributed)
2. Events published immediately (no outbox pattern yet)
3. Handlers are synchronous callables
4. Support for `subscribe(event_type, handler)` and `publish_all(events)`

### 8.2 Event Usage in Domain

**Pattern (from Course, Topic, LearningOutcome):**
```python
# In domain aggregate:
_events: list[DomainEvent] = field(default_factory=list, repr=False)

def archive(self) -> None:
    if self.status == Status.ARCHIVED:
        raise AlreadyArchivedError(...)
    self.status = Status.ARCHIVED
    self.touch()
    self._events.append(
        DomainEvent(
            event_type="course.archived",
            payload={"course_id": self.id.value},
        )
    )

def pull_events(self) -> list[DomainEvent]:
    events = list(self._events)
    self._events.clear()
    return events
```

**In repository/service:**
```python
# After saving aggregate:
await self.repository.save(course, tenant_id=tenant_id)

# Then publish any events:
events = course.pull_events()
self.event_bus.publish_all(events)
```

**Event Contracts (inferred from existing code):**
```
course.created
  payload: {course_id, department_id, code}

course.updated
  payload: {course_id}

course.archived
  payload: {course_id}

topic.created
  payload: {topic_id, course_id}

topic.updated
  payload: {topic_id}

topic.archived
  payload: {topic_id}

topic.published
  payload: {topic_id}

topic.learning_outcome_added
  payload: {topic_id, learning_outcome_id}

learning_outcome.created
  payload: {learning_outcome_id, topic_id}

learning_outcome.updated
  payload: {learning_outcome_id}

learning_outcome.archived
  payload: {learning_outcome_id}

learning_outcome.published
  payload: {learning_outcome_id}
```

**For Assessment Core:**
```
question.created
  payload: {question_id, topic_id, tenant_id, question_type, prompt, difficulty, marks}

question.updated
  payload: {question_id, topic_id}

question.archived
  payload: {question_id}

question.published
  payload: {question_id, topic_id}
```

---

## 9. Test Patterns

### 9.1 Domain Unit Tests

**Files:**
- [tests/domain/catalogue/test_course.py](tests/domain/catalogue/test_course.py)
- [tests/domain/catalogue/test_topic.py](tests/domain/catalogue/test_topic.py)
- [tests/domain/catalogue/test_learning_outcome.py](tests/domain/catalogue/test_learning_outcome.py)

**Pattern:**
```python
import pytest

def test_course_create_is_active_by_default() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Intro to CS"),
        slug=CourseSlug("intro-to-cs"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )

    assert course.is_active is True
    assert course.status.value == "active"
    assert len(course.pull_events()) == 1

def test_course_archive_twice_raises() -> None:
    course = Course.create(...)
    course.pull_events()

    course.archive()
    with pytest.raises(CourseAlreadyArchivedError):
        course.archive()

def test_course_update_details_emits_event() -> None:
    course = Course.create(...)
    course.pull_events()

    course.update_details(CourseTitle("Updated"), "desc")

    assert course.pull_events()[0].event_type == "course.updated"
```

**For Question:**
```python
@pytest.mark.parametrize("option_count", [0, 1, 3])
def test_mcq_requires_between_2_and_n_options(option_count: int):
    with pytest.raises(InvalidMCQError):
        Question.create(
            topic_id=TopicId(""),
            question_type=QuestionType.MCQ,
            prompt=Prompt("Question?"),
            explanation=Explanation("Explanation"),
            difficulty=Difficulty.EASY,
            marks=Marks(1),
            options=[
                # ... option_count options
            ]
        )

def test_mcq_requires_exactly_one_correct_option():
    with pytest.raises(InvalidMCQError):
        Question.create(
            ...,
            options=[
                {"text": "A", "display_order": 1, "is_correct": False},
                {"text": "B", "display_order": 2, "is_correct": False},
                {"text": "C", "display_order": 3, "is_correct": False},
            ]
        )

def test_archived_question_cannot_be_updated():
    question = Question.create(...)
    question.archive()
    question.pull_events()
    
    with pytest.raises(QuestionArchivedError):
        question.update_details(prompt=Prompt("New prompt"))
```

### 9.2 Repository Integration Tests

**Files:**
- [tests/integration/catalogue/test_course_repository.py](tests/integration/catalogue/test_course_repository.py)

**Pattern:**
```python
@pytest.mark.asyncio
async def test_course_repository_save_get_list(session):
    tenant_id = str(uuid.uuid4())
    faculty_id = str(uuid.uuid4())
    department_id = str(uuid.uuid4())

    # Set up tenant/faculty/department
    now = datetime.now(timezone.utc)
    tenant = TenantModel(id=tenant_id, name="T", slug="t", ...)
    faculty = FacultyModel(id=faculty_id, tenant_id=tenant_id, ...)
    department = DepartmentModel(id=department_id, tenant_id=tenant_id, faculty_id=faculty_id, ...)
    session.add_all([tenant, faculty, department])
    await session.flush()

    # Create domain aggregate
    repo = SqlAlchemyCourseRepository(session)
    course = Course.create(
        department_id=DepartmentId(department_id),
        code=CourseCode("CS101"),
        title=CourseTitle("Intro to CS"),
        # ...
    )
    topic = Topic.create(...)
    course.add_topic(topic)

    # Save and retrieve
    await repo.save(course, tenant_id=tenant_id)
    fetched = await repo.get_by_id(course.id.value, tenant_id=tenant_id)

    assert fetched is not None
    assert fetched.code.value == course.code.value
    assert len(fetched.topics) == 1
```

### 9.3 API/Integration Tests

**Files:**
- [tests/integration/catalogue/test_courses_api.py](tests/integration/catalogue/test_courses_api.py)
- [tests/integration/catalogue/test_tenant_scoped_writes.py](tests/integration/catalogue/test_tenant_scoped_writes.py)
- [tests/integration/catalogue/test_tenant_scoped_mutations.py](tests/integration/catalogue/test_tenant_scoped_mutations.py)

**Pattern:**
```python
@pytest.mark.asyncio
async def test_create_course_api(client, session):
    # Setup tenant/department
    tenant_id = str(uuid.uuid4())
    # ... create tenant, faculty, department models

    # Register user and get token
    auth_payload = {"email": f"user@example.com", "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=auth_payload)
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=auth_payload)
    access_token = authenticated.json()["data"]["access_token"]

    # Add user to tenant with role
    async with SessionLocal() as app_session:
        app_session.add(MembershipModel(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            role="lecturer",
            status="active",
        ))
        await app_session.commit()

    # Make API request with auth + tenant
    resp = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": "test-tenant",
        },
        json=payload,
    )

    assert resp.status_code == 201
    assert resp.json()["success"] is True

@pytest.mark.asyncio
async def test_student_cannot_create_course(client):
    # Setup student user in tenant
    _, tenant_slug, _, _, token = await seed_course_context(client, "student")

    resp = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json=course_payload(...),
    )

    assert resp.status_code == 403
    assert resp.json()["success"] is False

@pytest.mark.asyncio
async def test_lecturer_updates_course_in_own_tenant(client):
    tenant_id, tenant_slug, _, course_id, token = await seed_course_context(client)

    resp = client.patch(
        f"/catalogue/courses/{course_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json={"title": "Updated Title"},
    )

    assert resp.status_code == 200
    # Verify database
    async with SessionLocal() as session:
        course = await session.scalar(
            select(CourseModel).where(CourseModel.id == course_id)
        )
    assert course.tenant_id == tenant_id
    assert course.title == "Updated Title"

@pytest.mark.asyncio
async def test_cross_tenant_course_access_denied(client):
    _, tenant_a_slug, _, course_id, token_a = await seed_course_context(client)
    _, tenant_b_slug, _, _, _ = await seed_course_context(client)

    resp = client.get(
        f"/catalogue/courses/{course_id}",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-Slug": tenant_b_slug,  # Different tenant
        },
    )

    assert resp.status_code == 404  # Not 403 — resource doesn't exist in this tenant
```

**Key Test Patterns:**
1. Setup tenant/faculty/department via direct database insertion
2. Register user and get JWT token
3. Add user to tenant with role via membership
4. Make API request with `Authorization: Bearer <token>` and `X-Tenant-Slug: <slug>`
5. Verify response shape and HTTP status
6. Verify database state after mutation

---

## 10. Summary of Files for Question Implementation

| Layer | Category | File | Purpose |
|-------|----------|------|---------|
| **Domain** | Models | `app/domain/assessment/question.py` | Question aggregate root |
| | | `app/domain/assessment/value_objects.py` | QuestionId, QuestionType, Difficulty, Marks, Prompt, etc. |
| | | `app/domain/assessment/errors.py` | InvalidMCQError, QuestionAlreadyArchivedError, etc. |
| | Repositories | `app/domain/repositories/question.py` | QuestionRepository protocol |
| **Application** | Commands | `app/application/assessment/commands.py` | CreateQuestionCommand, UpdateQuestionCommand, ArchiveQuestionCommand |
| | Handlers | `app/application/assessment/handlers.py` | CreateQuestionHandler, UpdateQuestionHandler, ArchiveQuestionHandler |
| | Service | `app/application/assessment/question_service.py` | QuestionService facade |
| **Infrastructure** | Models | `app/infrastructure/db/models/assessment.py` | QuestionModel, QuestionOptionModel |
| | Repositories | `app/infrastructure/assessment/repositories.py` | SqlAlchemyQuestionRepository |
| | Mappers | `app/infrastructure/assessment/mappers.py` | question_to_domain, question_to_model, option_to_domain, option_to_model |
| | Unit of Work | `app/infrastructure/assessment/unit_of_work.py` | AssessmentUnitOfWork, assessment_unit_of_work context manager |
| **API** | Routes | `app/api/assessment/questions.py` | POST /assessment/questions, GET /assessment/questions/{id}, PATCH, POST archive |
| | Schemas | `app/api/assessment/schemas.py` | CreateQuestionRequest, QuestionResponse, QuestionOptionResponse, etc. |
| **Database** | Migrations | `alembic/versions/0006_add_assessment_schema_questions.py` | Create questions and question_options tables |
| **Tests** | Domain | `tests/domain/assessment/test_question.py` | MCQ invariants, archive rules, events |
| | Repository | `tests/integration/assessment/test_question_repository.py` | Persistence and tenant scoping |
| | Tenancy | `tests/integration/assessment/test_tenant_scoped_questions.py` | Cross-tenant rejection, multi-tenant isolation |
| | Authorization | `tests/integration/assessment/test_question_authorization.py` | Permission enforcement, role-based access |
| | API | `tests/integration/assessment/test_questions_api.py` | Full request/response lifecycle |

---

## 11. Architectural Constraints & Non-Negotiables

### DO
1. ✅ Use dataclass aggregates with `_events` list
2. ✅ Implement value objects with frozen dataclass + validation
3. ✅ Create separate repository protocol and SQLAlchemy implementation
4. ✅ Use mapper functions (to_domain, to_model)
5. ✅ Pass `tenant_id` explicitly to all repository/service methods
6. ✅ Enforce catalogue validation (Topic, LearningOutcome must be same-tenant)
7. ✅ Add tenant_id to every ORM model with FK + CASCADE
8. ✅ Create unique constraints combining `tenant_id + natural_key`
9. ✅ Use `selectinload()` to eager-load child entities
10. ✅ Emit domain events with aggregate_id and tenant_id in payload
11. ✅ Use async/await throughout (AsyncSession, async repository methods)
12. ✅ Validate permission at API layer with `require_permission(Permission.*)`
13. ✅ Return JSONResponse with standard envelope: `{success, data, meta, request_id}`
14. ✅ Validate request schemas with `extra="forbid"`
15. ✅ Use HTTP status codes: 401 (auth), 400 (tenant missing), 403 (permission), 404 (not found), 422 (validation), 201 (created), 200 (success)

### DON'T
1. ❌ Don't add tenant_id to domain models
2. ❌ Don't make QuestionOption an aggregate root
3. ❌ Don't create a new tenancy abstraction
4. ❌ Don't allow client-supplied tenant_id in request body
5. ❌ Don't filter tenant in Python — filter in database query
6. ❌ Don't implement soft-delete if catalogue uses archive pattern
7. ❌ Don't create synchronous methods in async-first codebase
8. ❌ Don't commit inside repository — let UoW manage transactions
9. ❌ Don't skip eager-loading relationships before mapping
10. ❌ Don't emit events before transaction commit
11. ❌ Don't expose `is_correct` in student-facing responses
12. ❌ Don't create new permission system — extend existing one
13. ❌ Don't modify catalogue models or repository
14. ❌ Don't implement QuestionBank, Assessment, Attempt, or later slices

---

## 12. Implementation Checklist

### Phase 1: Domain Model
- [ ] Create `app/domain/assessment/` directory
- [ ] Define QuestionId, QuestionType, Difficulty, Marks, Prompt, Explanation value objects
- [ ] Create Question aggregate with MCQ validation
- [ ] Create QuestionOption entity (embedded in Question)
- [ ] Define domain errors (InvalidMCQError, QuestionAlreadyArchivedError, InvalidLearningOutcomeError)
- [ ] Implement lifecycle: DRAFT → PUBLISHED → ARCHIVED
- [ ] Implement event emission (question.created, question.updated, question.archived)
- [ ] Write 10+ domain unit tests

### Phase 2: Persistence Layer
- [ ] Create QuestionModel and QuestionOptionModel in `app/infrastructure/db/models/assessment.py`
- [ ] Define foreign keys, constraints, indexes (tenant_id + natural keys)
- [ ] Create `app/infrastructure/assessment/` directory
- [ ] Implement SqlAlchemyQuestionRepository
- [ ] Implement mapper functions (question_to_domain, question_to_model, etc.)
- [ ] Create AssessmentUnitOfWork and context manager
- [ ] Create Alembic migration 0006 for questions and question_options tables
- [ ] Write repository integration tests

### Phase 3: Application Layer
- [ ] Create CreateQuestionCommand, UpdateQuestionCommand, ArchiveQuestionCommand
- [ ] Implement handlers with catalogue relationship validation
- [ ] Create QuestionService facade
- [ ] Validate topic exists, learning_outcome exists (same tenant, correct topic)
- [ ] Write handler tests

### Phase 4: Authorization & Events
- [ ] Add ASSESSMENT_* permissions to Permission enum
- [ ] Update ROLE_PERMISSIONS matrix
- [ ] Wire event bus subscription (if needed for Slice 1)
- [ ] Write authorization tests

### Phase 5: API Layer
- [ ] Create `app/api/assessment/` directory
- [ ] Create CreateQuestionRequest, QuestionResponse, QuestionOptionResponse schemas
- [ ] Implement POST /assessment/questions (create)
- [ ] Implement GET /assessment/questions/{id} (retrieve)
- [ ] Implement PATCH /assessment/questions/{id} (update)
- [ ] Implement POST /assessment/questions/{id}/archive (archive)
- [ ] Implement optional list endpoints if needed
- [ ] Add permission checks via `require_permission()`
- [ ] Write API integration tests

### Phase 6: Tenant Isolation & E2E Tests
- [ ] Test cross-tenant topic rejection
- [ ] Test cross-tenant learning_outcome rejection
- [ ] Test Tenant A cannot retrieve Tenant B question
- [ ] Test Tenant A cannot update Tenant B question
- [ ] Test student cannot create question
- [ ] Test lecturer can create/update in own tenant
- [ ] Test faculty_admin can archive
- [ ] Test event emission after creation

### Phase 7: Review & Cleanup
- [ ] Run all tests: `pytest -q`
- [ ] Verify no regressions in catalogue tests
- [ ] Check linting: `pylint app tests` (if configured)
- [ ] Verify type checking: `mypy app` (if configured)
- [ ] Run `git diff --check` for whitespace
- [ ] Confirm no catalogue behavior modified
- [ ] Document any new patterns in architecture ADR

---

## 13. Next Steps

**This inspection report is complete. Ready for:**

1. **User Review:** Verify the identified patterns match your understanding of the codebase
2. **Architecture Approval:** Confirm Question will implement exactly these patterns
3. **Implementation Authorization:** Proceed to Phase 2 (Design Check) and Phase 3 (Implementation)

**No code changes yet. This report establishes the reference baseline for Slice 1 implementation.**

---

**Report Generated:** 2026-08-22  
**Inspector:** Phase 1 Code Analysis  
**Status:** ✅ Ready for Review
