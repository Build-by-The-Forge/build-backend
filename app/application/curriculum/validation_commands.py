from dataclasses import dataclass


@dataclass(slots=True)
class ValidateBenchmarkCandidateCommand:
    curriculum_id: str
