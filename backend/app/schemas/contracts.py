from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, JsonValue

Severity = Literal['critical', 'high', 'medium', 'low']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IncidentCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    error_log: str = Field(min_length=10, max_length=50000)
    mode: Literal['demo', 'live'] = 'demo'
    repository: Literal['sample', 'local', 'github'] = 'sample'
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
    retrieval: dict = Field(default_factory=dict)
    id: str
    kind: Literal['source', 'log']
    path: str
    line_start: int
    line_end: int
    content: str
    sha256: str
    content_sha256: str = ''
    snapshot_id: str = ''
    commit_sha: str | None = None


class Citation(StrictModel):
    evidence_id: str
    kind: Literal['source', 'log']
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=8000)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    snapshot_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    commit_sha: str | None


class Observation(StrictModel):
    statement: str = Field(min_length=1, max_length=2000)
    citations: list[Citation] = Field(min_length=1, max_length=5)


class Hypothesis(StrictModel):
    title: str
    explanation: str
    confidence: Literal['high', 'medium', 'low']
    evidence_ids: list[str]
    uncertainty: str
    supporting_evidence: list[Citation] = Field(default_factory=list, max_length=10)
    contradicting_evidence: list[Citation] = Field(default_factory=list, max_length=10)
    missing_checks: list[str] = Field(default_factory=list, max_length=10)


class Analysis(StrictModel):
    observed_facts: list[str]
    hypotheses: list[Hypothesis] = Field(max_length=3)
    summary: str
    observations: list[Observation] = Field(default_factory=list, max_length=20)
    disposition: Literal['supported', 'insufficient_evidence'] = 'insufficient_evidence'


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
    provider: Literal['openai', 'gemini'] = 'openai'
    source_retrieval: Literal['stack', 'symbols'] = 'symbols'
    retrieval_mode: Literal['keyword', 'hybrid'] = 'hybrid'
    model: str = Field(default='gpt-4.1-mini', pattern=r'^[a-zA-Z0-9._:-]{1,100}$')
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    max_evidence_files: int = Field(default=5, ge=1, le=10)
    default_mode: Literal['demo', 'live'] = 'demo'

    @model_validator(mode='after')
    def matching_provider(self):
        if (self.provider == 'gemini') != self.model.startswith('gemini-'):
            raise ValueError('Choose a model belonging to the selected provider.')
        return self


class PullRequestRequest(StrictModel):
    authorized: Literal[True]


class ReproductionExpectation(StrictModel):
    test_id: str = Field(pattern=r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}$', max_length=240)
    expected_exception: str = Field(pattern=r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$', max_length=120)


class VerificationSpecification(StrictModel):
    version: Literal[1] = 1
    reviewed: Literal[True]
    rationale: str = Field(min_length=10, max_length=1000)
    reproduction: list[ReproductionExpectation] = Field(min_length=1, max_length=20)
    regressions: list[str] = Field(min_length=1, max_length=40)

    @model_validator(mode='after')
    def unique_tests(self):
        import re
        ids = [item.test_id for item in self.reproduction]
        if len(set(ids)) != len(ids) or len(set(self.regressions)) != len(self.regressions):
            raise ValueError('Test IDs must be unique within each test role.')
        if any(len(value) > 240 or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}', value) for value in self.regressions):
            raise ValueError('Use dotted unittest IDs: module.Class.test_method.')
        return self


class JsonContractCase(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')
    role: Literal['reproduction', 'regression']
    input: JsonValue
    baseline: JsonValue
    expected: JsonValue


class JsonContract(StrictModel):
    version: Literal[1] = 1
    reviewed: Literal[True]
    entrypoint: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=10, max_length=1000)
    cases: list[JsonContractCase] = Field(min_length=2, max_length=4)

    @model_validator(mode='after')
    def bounded_contract(self):
        import json
        if {c.role for c in self.cases} != {'reproduction', 'regression'} or len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError('Include distinct case IDs and both reproduction and regression cases.')
        for case in self.cases:
            values = [json.dumps(v, sort_keys=True, allow_nan=False) for v in (case.input, case.baseline, case.expected)]
            if any(len(v.encode()) > 4096 for v in values):
                raise ValueError('Contract values must fit within 4 KiB each.')
            if (values[1] == values[2]) != (case.role == 'regression'):
                raise ValueError('Reproduction baseline must differ from expected; regression baseline must equal expected.')
        return self


class ValidationPlanRequest(StrictModel):
    files: list[str] = Field(min_length=1, max_length=32)
    profile: Literal['python-unittest', 'python-pytest', 'python-json-stdio'] = 'python-unittest'
    verification_spec: VerificationSpecification | None = None
    json_contract: JsonContract | None = None
    registered_contract_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def specification_profile(self):
        if self.verification_spec and self.profile != 'python-unittest':
            raise ValueError('Reviewed verification specifications currently require unittest.')
        if self.json_contract is not None and self.registered_contract_sha256 is not None:
            raise ValueError('Choose either an ad hoc contract or an immutable registered contract.')
        if (self.json_contract is not None or self.registered_contract_sha256 is not None) != (self.profile == 'python-json-stdio'):
            raise ValueError('The JSON profile requires a JSON contract, and other profiles cannot use one.')
        return self


class ContractRegistration(StrictModel):
    files: list[str] = Field(min_length=1, max_length=32)
    contract: JsonContract


class ContractReview(StrictModel):
    registration_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewed: Literal[True]
    rationale: str = Field(min_length=10, max_length=1000)


class ValidationAuthorization(StrictModel):
    authorized: Literal[True]
    plan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class RepairOutcome(StrictModel):
    status: Literal['VERIFIED', 'PATCH_UNVERIFIED', 'NOT_REPRODUCED', 'VALIDATION_FAILED', 'INSUFFICIENT_EVIDENCE']
    reasons: list[str]
    validation_run_id: str | None = None
