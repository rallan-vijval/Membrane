/**
 * API types for the Membrane review UI, aligned by hand with contracts/openapi.yaml
 * (review API v1, branch feat/membrane-backend, commit d5e4c73).
 * If the contract changes, update this file, http.ts and synthetic.ts together.
 * Conventions: string IDs, snake_case JSON, UTC ISO timestamps, integer cents.
 */

export type CandidateStatus = 'staged' | 'testing' | 'eligible' | 'quarantined' | 'inconclusive' | 'approved';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'inconclusive';
export type Admission = 'eligible' | 'quarantine' | 'inconclusive';
export type Side = 'baseline' | 'candidate';
export type Repetition = 1 | 2;
export type HealthStatus = 'ready' | 'unavailable' | 'degraded' | 'disabled';
export type ScopeKind = 'global' | 'order' | 'preference';
export type Action = 'refund_order' | 'request_return' | 'request_verification' | 'answer';
export type Classification =
  | 'unchanged-safe'
  | 'intended-safe-change'
  | 'new-policy-violation'
  | 'pre-existing-violation'
  | 'inconclusive';

export interface ComponentHealth {
  status: HealthStatus;
  reason: string;
}

export interface Health {
  database: ComponentHealth;
  model: ComponentHealth;
  search: ComponentHealth;
  voice: ComponentHealth;
  demo_identity?: string;
  workspace_id: string;
}

export interface Scope {
  kind?: ScopeKind;
  order_id?: string | null;
  customer_id?: string | null;
  exception_id?: string | null;
}

export interface Source {
  source_id: string;
  created_at: string;
  sha256: string;
  mime_type: string;
  image_url: string;
  extracted_text: string;
  quotation: string;
  proposed_text: string;
  proposed_scope: Scope;
  trust?: 'untrusted';
  provenance: Record<string, unknown>;
}

export interface Candidate {
  candidate_id: string;
  created_at: string;
  source_id: string;
  text: string;
  scope: Scope;
  parent_candidate_id: string | null;
  base_version_id: string;
  content_hash: string;
  status: CandidateStatus;
  latest_run_id?: string | null;
}

export interface CandidateList {
  items: Candidate[];
  truncated: boolean;
}

export interface Attempt {
  action: Action;
  answer: string;
  arguments?: Record<string, unknown> | null;
}

export interface Check {
  code: string;
  passed: boolean;
  reason: string;
}

/** Result of the deterministic tool guard. Present only when a refund was attempted. */
export interface ToolOutcome {
  allowed?: boolean;
  reasons?: string[];
  simulated?: boolean;
}

export interface Execution {
  side: Side;
  repetition: Repetition;
  raw_responses: Record<string, unknown>[];
  attempt: Attempt | null;
  tool_outcome: ToolOutcome | null;
  checks: Check[];
  error: string | null;
  input_hash: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

export interface CaseEvidence {
  case_id: string;
  classification: Classification;
  executions: Execution[];
}

export interface SelectedCase {
  case_id: string;
  description: string;
  reasons: string[];
  semantic_score: number | null;
  task: Record<string, unknown>;
}

export interface Run {
  run_id: string;
  candidate_id: string;
  created_at: string;
  status: RunStatus;
  admission: Admission | null;
  reasons: string[];
  progress: { completed?: number; total?: number };
  selection: SelectedCase[];
  selection_metadata: Record<string, unknown>;
  cases: CaseEvidence[];
  summary: Record<string, unknown>;
  config: Record<string, unknown>;
  usage: Record<string, unknown>;
  live?: boolean;
  base_version_id: string;
  candidate_hash: string;
}

export interface MemoryEntry {
  text?: string;
  scope?: Scope;
  candidate_id?: string | null;
}

export interface Version {
  version_id: string;
  created_at: string;
  parent_version_id: string | null;
  memories: MemoryEntry[];
  candidate_id?: string | null;
  run_id?: string | null;
  policy_hash: string;
}

export interface ReviewEvent {
  event_id: string;
  created_at: string;
  actor: string;
  decision: string;
  candidate_id: string;
  run_id: string | null;
  version_id: string | null;
  reason: string;
}

export interface History {
  versions: Version[];
  events: ReviewEvent[];
  truncated: boolean;
}

export interface Audio {
  audio_id: string;
  audio_url: string;
  transcript: string;
  cached: boolean;
}

export interface ErrorResponse {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Everything the UI needs from the backend. Implemented by http.ts (real) and synthetic.ts. */
export interface MembraneApi {
  readonly mode: 'real' | 'synthetic';
  /** Turns a backend-relative URL (image_url, audio_url) into one the browser can load. */
  asset(url: string): string;
  health(): Promise<Health>;
  uploadSource(file: File): Promise<Source>;
  getSource(sourceId: string): Promise<Source>;
  listCandidates(): Promise<CandidateList>;
  createCandidate(input: { source_id: string; text: string; scope: Scope; base_version_id: string }): Promise<Candidate>;
  getCandidate(candidateId: string): Promise<Candidate>;
  startRun(candidateId: string): Promise<{ run_id: string }>;
  getRun(runId: string): Promise<Run>;
  revise(candidateId: string, input: { text: string; scope: Scope }): Promise<Candidate>;
  approve(candidateId: string, input: { run_id: string; reason: string }): Promise<Candidate>;
  quarantine(candidateId: string, reason: string): Promise<Candidate>;
  activeMemory(): Promise<Version>;
  history(): Promise<History>;
  audio(runId: string, caseId: string, side: Side, repetition: Repetition): Promise<Audio>;
}

export const TERMINAL_RUN: ReadonlySet<RunStatus> = new Set<RunStatus>(['completed', 'failed', 'inconclusive']);
