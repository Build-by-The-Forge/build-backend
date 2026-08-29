from dataclasses import dataclass


@dataclass(slots=True)
class ActivateBenchmarkCurriculumCommand:
    curriculum_id: str
    activated_by: str | None = None
