"""Public v1 API DTOs. OpenAPI is generated from these models, not hand-maintained."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scope(DTO):
    kind: Literal["global", "order", "preference"] = "global"
    order_id: str | None = None
    customer_id: str | None = None
    exception_id: str | None = None

    @model_validator(mode="after")
    def exact_scope(self):
        if self.kind == "order":
            if not self.order_id or not self.order_id.strip() or not self.customer_id or not self.customer_id.strip():
                raise ValueError("Order scope requires exact order and customer IDs")
        elif any(v is not None for v in (self.order_id, self.customer_id, self.exception_id)):
            raise ValueError("Global/preference scope cannot carry order authority")
        return self


class CandidateIn(DTO):
    source_id: str
    text: str = Field(min_length=1, max_length=8000)
    scope: Scope
    base_version_id: str
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, strict=True)


class ReviseIn(DTO):
    text: str = Field(min_length=1, max_length=8000)
    scope: Scope
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, strict=True)


class ApproveIn(DTO):
    run_id: str
    reason: str = Field(min_length=1, max_length=2000)


class QuarantineIn(DTO):
    reason: str = Field(min_length=1, max_length=2000)


class AudioIn(DTO):
    side: Literal["baseline", "candidate"]
    repetition: Literal[1, 2]


class ComponentHealth(DTO):
    status: Literal["ready", "unavailable", "degraded", "disabled"]
    reason: str


class Health(DTO):
    database: ComponentHealth
    model: ComponentHealth
    search: ComponentHealth
    voice: ComponentHealth
    embeddings: ComponentHealth = Field(default_factory=lambda: ComponentHealth(status="unavailable", reason="Embedding access unverified"))
    memory_search: ComponentHealth = Field(default_factory=lambda: ComponentHealth(status="disabled", reason="Governed memory is not enabled"))
    tracing: ComponentHealth = Field(default_factory=lambda: ComponentHealth(status="disabled", reason="Optional tracing disabled"))
    vision: ComponentHealth = Field(default_factory=lambda: ComponentHealth(status="unavailable", reason="Vision access unverified"))
    transcription: ComponentHealth = Field(default_factory=lambda: ComponentHealth(status="disabled", reason="Optional transcription disabled"))
    demo_identity: str = "Local demo reviewer"
    workspace_id: str


class Source(DTO):
    source_id: str
    created_at: str
    sha256: str
    mime_type: str
    image_url: str | None
    source_kind: Literal["image", "audio"] = "image"
    audio_source_id: str | None = None
    audio_url: str | None = None
    extracted_text: str
    quotation: str
    proposed_text: str
    proposed_scope: Scope
    trust: Literal["untrusted"] = "untrusted"
    provenance: dict[str, Any]


CandidateStatus = Literal["staged", "testing", "eligible", "quarantined", "inconclusive", "approved"]


class Candidate(DTO):
    candidate_id: str
    created_at: str
    source_id: str
    text: str
    scope: Scope
    parent_candidate_id: str | None
    base_version_id: str
    content_hash: str
    status: CandidateStatus
    latest_run_id: str | None = None
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class CandidateList(DTO):
    items: list[Candidate]
    truncated: bool


class Version(DTO):
    version_id: str
    created_at: str
    parent_version_id: str | None
    memories: list[dict[str, Any]]
    candidate_id: str | None = None
    run_id: str | None = None
    policy_hash: str


class ReviewEvent(DTO):
    event_id: str
    created_at: str
    actor: str
    decision: str
    candidate_id: str
    run_id: str | None
    version_id: str | None
    reason: str
    memory_id: str | None = None
    base_version_id: str | None = None


class History(DTO):
    versions: list[Version]
    events: list[ReviewEvent]
    truncated: bool


class Check(DTO):
    code: str
    passed: bool
    reason: str


class Attempt(DTO):
    action: Literal["refund_order", "request_return", "request_verification", "answer"]
    answer: str
    arguments: dict[str, Any] | None = None


class Execution(DTO):
    side: Literal["baseline", "candidate"]
    repetition: Literal[1, 2]
    raw_responses: list[dict[str, Any]]
    attempt: Attempt | None
    tool_outcome: dict[str, Any] | None
    checks: list[Check]
    error: str | None
    input_hash: str
    calls: int
    input_tokens: int
    output_tokens: int
    latency_ms: int
    trace_url: str | None = None


class SelectedCase(DTO):
    case_id: str
    description: str
    reasons: list[str]
    semantic_score: float | None
    task: dict[str, Any]


class CaseEvidence(DTO):
    case_id: str
    classification: Literal["unchanged-safe", "intended-safe-change", "new-policy-violation", "pre-existing-violation", "inconclusive"]
    executions: list[Execution]


class MemoryEntry(DTO):
    memory_id: str
    text: str
    content_hash: str
    scope: Scope
    candidate_id: str
    version_id: str
    activated_at: str
    expires_at: str


class MemoryEntryView(MemoryEntry):
    availability: Literal["active", "expired"]


class MemoryEntries(DTO):
    version_id: str
    evaluated_at: str
    items: list[MemoryEntryView]
    truncated: bool = False


class RetrievedMemory(MemoryEntry):
    reason: Literal["exact_scope", "semantic"]
    semantic_score: float | None


class MemoryRetrieval(DTO):
    case_id: str
    retrieval_at: str
    profile_id: str
    base_version_id: str
    entries: list[RetrievedMemory]
    usage: dict[str, Any] = Field(default_factory=dict)


class RevokeIn(DTO):
    base_version_id: str
    reason: str = Field(min_length=1, max_length=2000)


class RevokeResult(DTO):
    version_id: str
    event_id: str


class TaskOption(DTO):
    fixture_id: str
    description: str


class TaskOptions(DTO):
    items: list[TaskOption]
    truncated: bool


class ExecuteActiveIn(DTO):
    base_version_id: str


class ActiveExecution(DTO):
    execution_id: str
    created_at: str
    version_id: str
    fixture_id: str
    retrieval: MemoryRetrieval
    execution: Execution
    config: dict[str, Any]
    usage: dict[str, Any]
    trace_url: str | None = None


class Run(DTO):
    run_id: str
    candidate_id: str
    created_at: str
    status: Literal["queued", "running", "completed", "failed", "inconclusive"]
    admission: Literal["eligible", "quarantine", "inconclusive"] | None
    reasons: list[str]
    progress: dict[str, int]
    selection: list[SelectedCase]
    selection_metadata: dict[str, Any]
    cases: list[CaseEvidence]
    summary: dict[str, Any]
    config: dict[str, Any]
    usage: dict[str, Any]
    live: bool = True
    base_version_id: str
    candidate_hash: str
    memory_retrieval: list[MemoryRetrieval] = Field(default_factory=list)
    trace_url: str | None = None


class RunAccepted(DTO):
    run_id: str


class Audio(DTO):
    audio_id: str
    audio_url: str
    transcript: str
    cached: bool


class ErrorDetail(DTO):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(DTO):
    error: ErrorDetail


class AudioWord(DTO):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)

class AudioSource(DTO):
    audio_source_id: str
    created_at: str
    status: Literal["processing", "transcribed", "failed"]
    sha256: str
    duration_seconds: float
    audio_url: str
    transcript: str = ""
    words: list[AudioWord] = Field(default_factory=list)
    model: str
    language: str | None = None
    error: str | None = None
    trust: Literal["untrusted"] = "untrusted"

class ReviewAudioIn(DTO):
    reviewed_text: str = Field(min_length=1, max_length=16000)

class ScopeExperimentIn(DTO):
    base_version_id: str

class ScopeScenario(DTO):
    scenario_id: str
    title: str
    changed_fields: dict[str, Any]
    task: dict[str, Any]
    policy_snapshot: dict[str, Any]
    expected_action: str
    rule: str
    fixture_hash: str
    retrieval: MemoryRetrieval

class ExperimentCase(CaseEvidence):
    repetition_consistent: bool


class ScopeExperiment(DTO):
    experiment_id: str
    candidate_id: str
    created_at: str
    status: Literal["queued", "running", "completed", "inconclusive", "failed"]
    admission_evidence: Literal[False] = False
    candidate_hash: str
    base_version_id: str
    profile_id: str
    config: dict[str, Any]
    evaluated_at: str
    scenarios: list[ScopeScenario]
    progress: dict[str, int]
    cases: list[ExperimentCase] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    stress_test: str = "Proposal added to every experimental request, including requests outside its scope. Not normal production retrieval."

class ExperimentAccepted(DTO):
    experiment_id: str
