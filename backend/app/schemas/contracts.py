from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Severity = Literal['critical', 'high', 'medium', 'low']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IncidentCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    error_log: str = Field(min_length=10, max_length=50000)
    mode: Literal['demo', 'live'] = 'demo'
    repository: Literal['sample', 'local'] = 'sample'
    selected_files: list[str] = Field(default_factory=list, max_length=10)


class Frame(StrictModel):
    path: str
    line: int
    function: str


class Triage(StrictModel):
    exception: str
    severity: Severity
    service: str
    message: str
    timestamps: list[str]
    frames: list[Frame]


class Evidence(StrictModel):
    id: str
    kind: Literal['source', 'log']
    path: str
    line_start: int
    line_end: int
    content: str
    sha256: str


class Hypothesis(StrictModel):
    title: str
    explanation: str
    confidence: Literal['high', 'medium', 'low']
    evidence_ids: list[str]
    uncertainty: str


class Analysis(StrictModel):
    observed_facts: list[str]
    hypotheses: list[Hypothesis]
    summary: str


class FileChange(StrictModel):
    path: str
    proposed_code: str = Field(max_length=80000)


class FixSuggestion(FileChange):
    files: list[FileChange] = Field(default_factory=list, max_length=5)
    explanation: str
    risks: list[str]


class ReportNarrative(StrictModel):
    summary: str
    risk_assessment: str
    next_steps: list[str]


class Decision(StrictModel):
    note: str = Field(default='', max_length=2000)


class Resolution(StrictModel):
    note: str = Field(min_length=10, max_length=2000)
    evidence: str = Field(min_length=10, max_length=2000)


class Reopen(StrictModel):
    note: str = Field(min_length=10, max_length=2000)


class Preferences(StrictModel):
    retrieval_mode: Literal['keyword', 'hybrid'] = 'hybrid'
    model: str = Field(default='gpt-4.1-mini', pattern=r'^[a-zA-Z0-9._:-]{1,100}$')
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    max_evidence_files: int = Field(default=5, ge=1, le=10)
    default_mode: Literal['demo', 'live'] = 'demo'


class PullRequestRequest(StrictModel):
    authorized: Literal[True]


class ValidationPlanRequest(StrictModel):
    files: list[str] = Field(min_length=1, max_length=32)
    profile: Literal['python-unittest', 'python-pytest'] = 'python-unittest'


class ValidationAuthorization(StrictModel):
    authorized: Literal[True]
    plan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
