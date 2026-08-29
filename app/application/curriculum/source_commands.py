from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RegisterCurriculumSourceCommand:
    code: str
    name: str
    base_url: str
    source_type: str = "official_benchmark"
    sync_frequency_days: int = 30
    parser_version: str = "v1.0"


@dataclass(slots=True)
class GetCurriculumSourceCommand:
    source_id: str


@dataclass(slots=True)
class ListCurriculumSourcesCommand:
    status: str | None = None


@dataclass(slots=True)
class RecordCurriculumSnapshotCommand:
    source_id: str
    source_url: str
    content_sha256: str
    raw_artifact_uri: str
    parser_version: str | None = None
    retrieved_at: datetime | None = None


@dataclass(slots=True)
class ListCurriculumSnapshotsCommand:
    source_id: str
    limit: int = 50
    offset: int = 0
