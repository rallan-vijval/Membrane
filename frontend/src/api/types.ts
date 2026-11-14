/**
 * API types for the Membrane review UI.
 *
 * UI view models shared by real and synthetic modes. Wire DTOs are generated from
 * contracts/openapi.yaml in generated.ts; normalize.ts explicitly maps them here.
 */

export type CandidateState = 'staged' | 'testing' | 'eligible' | 'quarantined' | 'inconclusive' | 'approved';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'inconclusive';
export type Admission = 'eligible' | 'quarantine' | 'inconclusive';
export type Side = 'baseline' | 'candidate';
export type Repetition = 1 | 2;
export type HealthStatus = 'ready' | 'unavailable' | 'degraded' | 'disabled';

export interface IntegrationHealth {
  status: HealthStatus;
  detail: string | null;
}

export interface Health {
  database: IntegrationHealth;
  model: IntegrationHealth;
  search: IntegrationHealth;
  voice: IntegrationHealth;
  /** Governed-memory phase components. Absent on a backend that predates them. */
  embeddings?: IntegrationHealth;
  memory_search?: IntegrationHealth;
  tracing?: IntegrationHealth;
  vision?: IntegrationHealth;
}

export type Scope =
  | { kind: 'global' }
  | { kind: 'preference' }
  | { kind: 'order'; order_id: string; customer_id: string | null; exception_id?: string | null };

export interface Source {
  id: string;
  extracted_text: string;
  quotation: string | null;
  proposed_candidate: { text: string; scope: Scope } | null;
  provenance: {
    sha256: string;
    mime_type: string;
    extraction_model: string | null;
    trusted: boolean;
  };
  image_url: string | null;
  created_at: string;
}

export interface Candidate {
  id: string;
  source_id: string;
  text: string;
  scope: Scope;
  state: CandidateState;
  parent_candidate_id: string | null;
  base_version_id: string;
  content_hash: string;
  latest_run_id: string | null;
  created_at: string;
  /** How long the memory lives once activated. Part of the candidate's frozen content hash. */
  ttl_seconds: number;
}

export const TTL_DEFAULT_SECONDS = 3600;
export const TTL_MIN_SECONDS = 60;
export const TTL_MAX_SECONDS = 86400;

export type SelectionReason = 'sentinel' | 'vector' | 'neighbor' | 'fill';

export interface SelectedFixture {
  fixture_id: string;
  title: string;
  reason: SelectionReason;
  score: number | null;
  reasons?: string[];
}

export type Classification =
  | 'unchanged-safe'
  | 'intended-safe-change'
  | 'new-policy-violation'
  | 'pre-existing-violation'
  | 'inconclusive';

export type Outcome = 'refund' | 'request_return' | 'request_verification' | 'answer' | 'error';

export interface Execution {
  side: Side;
  repetition: Repetition;
  outcome: Outcome;
  answer_text: string;
  /** Exact tool arguments the agent attempted, before enforcement. */
  attempt: { tool: string; arguments: Record<string, unknown> } | null;
  /** Deterministic policy enforcement against trusted task facts. */
  enforcement: { allowed: boolean; reasons: string[] } | null;
  error: string | null;
  raw_responses?: Record<string, unknown>[];
  checks?: { code: string; passed: boolean; reason: string }[];
}

export interface CaseResult {
  case_id: string;
  fixture_id: string;
  title: string;
  classification: Classification | null;
  check_reasons: string[];
  executions: Execution[];
}

export interface Run {
  id: string;
  candidate_id: string;
  status: RunStatus;
  admission: Admission | null;
  progress: { completed: number; total: number };
  selection: SelectedFixture[];
  cases: CaseResult[];
  reasons: string[];
  errors: string[];
  model_config: { provider: string; agent_model: string; temperature: number | null };
  usage: { model_calls: number; input_tokens: number; output_tokens: number; latency_ms: number };
  /** true when the evidence is a stored recording, not a live model run. */
  recorded: boolean;
  created_at: string;
  completed_at: string | null;
  /** Memories frozen for each selected case. Empty on runs that predate retrieval provenance. */
  memory_retrieval: CaseRetrieval[];
  trace_url: string | null;
}

/** One governed memory as the backend evaluates it right now. */
export interface GovernedEntry {
  id: string;
  text: string;
  scope: Scope;
  candidate_id: string | null;
  version_id: string;
  activated_at: string;
  expires_at: string;
  availability: 'active' | 'expired';
}

export interface GovernedMemory {
  version_id: string;
  /** The backend's clock when availability was decided. The authority, not the browser clock. */
  evaluated_at: string;
  items: GovernedEntry[];
  truncated: boolean;
}

export interface RetrievedMemory extends GovernedEntry {
  reason: 'exact_scope' | 'semantic';
  score: number | null;
}

/** Which memories the agent was given for one case, frozen once and reused for both sides. */
export interface CaseRetrieval {
  case_id: string;
  retrieval_at: string;
  profile_id: string;
  base_version_id: string;
  entries: RetrievedMemory[];
}

export interface TaskOption {
  fixture_id: string;
  description: string;
}

/** One bounded run of the live agent with ACTIVE memory. Never admission evidence. */
export interface ActiveExecution {
  id: string;
  created_at: string;
  version_id: string;
  fixture_id: string;
  retrieval: CaseRetrieval;
  execution: Execution;
  model: string | null;
  trace_url: string | null;
}

export interface MemoryEntry {
  id: string;
  text: string;
  scope: Scope;
  candidate_id: string | null;
}

export interface ActiveMemory {
  version_id: string;
  revision: number | null;
  entries: MemoryEntry[];
  activated_at: string;
}

export interface VersionRecord {
  version_id: string;
  parent_version_id: string | null;
  candidate_id: string | null;
  run_id: string | null;
  activated_at: string;
}

export interface ReviewEvent {
  id: string;
  decision: 'approve' | 'quarantine' | 'revise' | 'revoke';
  actor: string;
  candidate_id: string;
  run_id: string | null;
  version_id: string | null;
  reason: string | null;
  created_at: string;
  /** Set on revoke events. */
  memory_id?: string | null;
}

export interface History {
  versions: VersionRecord[];
  events: ReviewEvent[];
  truncated: boolean;
}

export interface AudioClip {
  transcript: string;
  audio_url: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: unknown = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Everything the UI needs from the backend. Implemented by http.ts (real) and synthetic.ts. */
export interface MembraneApi {
  readonly mode: 'real' | 'synthetic';
  health(): Promise<Health>;
  uploadSource(file: File): Promise<Source>;
  getSource(id: string): Promise<Source>;
  createCandidate(input: { source_id: string; text: string; scope: Scope; base_version_id: string; ttl_seconds: number }): Promise<Candidate>;
  getCandidate(id: string): Promise<Candidate>;
  /** Latest candidates, newest first as the backend returns them. */
  listCandidates(): Promise<Candidate[]>;
  startRun(candidateId: string): Promise<{ run_id: string }>;
  getRun(id: string): Promise<Run>;
  revise(candidateId: string, input: { text: string; scope: Scope; ttl_seconds: number }): Promise<Candidate>;
  approve(candidateId: string, runId: string): Promise<Candidate>;
  quarantine(candidateId: string, reason: string): Promise<Candidate>;
  activeMemory(): Promise<ActiveMemory>;
  history(): Promise<History>;
  audio(runId: string, caseId: string, side: Side, repetition: Repetition): Promise<AudioClip>;
  memoryEntries(): Promise<GovernedMemory>;
  revokeMemory(memoryId: string, input: { base_version_id: string; reason: string }): Promise<{ version_id: string; event_id: string }>;
  listTasks(): Promise<TaskOption[]>;
  executeTask(fixtureId: string, baseVersionId: string): Promise<ActiveExecution>;
  getExecution(executionId: string): Promise<ActiveExecution>;
}

export const TERMINAL_RUN: ReadonlySet<RunStatus> = new Set<RunStatus>(['completed', 'failed', 'inconclusive']);
