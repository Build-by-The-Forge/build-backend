from dataclasses import dataclass


@dataclass(slots=True)
class CompareBenchmarkCurriculaCommand:
    source_curriculum_id: str
    target_curriculum_id: str
