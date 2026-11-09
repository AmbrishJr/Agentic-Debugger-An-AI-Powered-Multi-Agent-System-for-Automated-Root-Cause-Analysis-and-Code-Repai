from typing import Literal
from pydantic import Field, model_validator
from app.schemas.contracts import StrictModel


class EvaluationInput(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9-]+$')
    split: Literal['development', 'held-out']
    title: str
    error_log: str
    sources: dict[str, str]
    selected_files: list[str]
    repository: Literal['sample', 'local'] = 'local'
    language: str = 'python'
    environment: dict[str, str] = Field(default_factory=lambda: {'test_profile': 'python-unittest', 'dependencies': 'standard-library'})
    privacy: Literal['synthetic'] = 'synthetic'
    difficulty: Literal['easy', 'medium'] = 'easy'


class EvaluationOracle(StrictModel):
    id: str
    cause: str | None
    files: list[str]
    expected_evidence: list[str]
    uncertain: bool
    repair_eligible: bool
    tests: dict[str, str]
    reference_patch: dict[str, str]

    @model_validator(mode='after')
    def executable_repair(self):
        if self.repair_eligible and (not self.tests or not self.reference_patch or not self.cause):
            raise ValueError('Repair-eligible cases require independent tests, a reference patch and a cause.')
        return self


class EvaluationDataset(StrictModel):
    version: Literal[1]
    cases: list[EvaluationInput]


class OracleDataset(StrictModel):
    version: Literal[1]
    cases: list[EvaluationOracle]


class Adjudication(StrictModel):
    case_id: str
    prediction_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    correct: bool
    reviewer: str = Field(min_length=1)
    rationale: str = Field(min_length=10)
