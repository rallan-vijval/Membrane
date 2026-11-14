/**
 * Wire shapes and adapters for the governed-memory phase, written by hand from
 * contracts/openapi.yaml at backend commit a025e71 (branch feat/governed-memory-backend).
 *
 * Why not generated.ts: that file is produced by `npm run generate:api` from the contract in
 * this checkout, and the new contract is not merged into this branch yet. After the merge,
 * regenerate and replace these interfaces with `components['schemas'][...]`; the adapters stay.
 */
import type { components } from './generated';
import { executionFromWire, scopeFromWire } from './normalize';
import type { ActiveExecution, CaseRetrieval, GovernedEntry, GovernedMemory, RetrievedMemory, TaskOption } from './types';

type DTO = components['schemas'];

export interface WireMemoryEntry {
  memory_id: string;
  text: string;
  content_hash: string;
  scope: DTO['Scope'];
  candidate_id: string;
  version_id: string;
  activated_at: string;
  expires_at: string;
  availability?: 'active' | 'expired';
}
export interface WireMemoryEntries { version_id: string; evaluated_at: string; items: WireMemoryEntry[]; truncated?: boolean }
export interface WireRetrievedMemory extends WireMemoryEntry { reason: 'exact_scope' | 'semantic'; semantic_score: number | null }
export interface WireMemoryRetrieval { case_id: string; retrieval_at: string; profile_id: string; base_version_id: string; entries: WireRetrievedMemory[]; usage?: Record<string, unknown> }
export interface WireTaskOptions { items: { fixture_id: string; description: string }[]; truncated: boolean }
export interface WireActiveExecution {
  execution_id: string; created_at: string; version_id: string; fixture_id: string;
  retrieval: WireMemoryRetrieval; execution: DTO['Execution']; config: Record<string, unknown>; usage: Record<string, unknown>; trace_url?: string | null;
}
export interface WireRevokeResult { version_id: string; event_id: string }

const entryFromWire = (m: WireMemoryEntry, evaluatedAt: string): GovernedEntry => ({
  id: m.memory_id, text: m.text, scope: scopeFromWire(m.scope), candidate_id: m.candidate_id || null, version_id: m.version_id,
  activated_at: m.activated_at, expires_at: m.expires_at,
  // The backend decides availability. Only if it is absent (retrieved entries) compare against the backend's own timestamp.
  availability: m.availability ?? (Date.parse(m.expires_at) > Date.parse(evaluatedAt) ? 'active' : 'expired'),
});

export const memoryFromWire = (value: WireMemoryEntries): GovernedMemory => ({
  version_id: value.version_id, evaluated_at: value.evaluated_at,
  items: value.items.map((m) => entryFromWire(m, value.evaluated_at)), truncated: value.truncated === true,
});

export const retrievalFromWire = (value: WireMemoryRetrieval): CaseRetrieval => ({
  case_id: value.case_id, retrieval_at: value.retrieval_at, profile_id: value.profile_id, base_version_id: value.base_version_id,
  entries: value.entries.map((m): RetrievedMemory => ({ ...entryFromWire(m, value.retrieval_at), reason: m.reason, score: m.semantic_score })),
});

export const tasksFromWire = (value: WireTaskOptions): TaskOption[] =>
  value.items.map((t) => ({ fixture_id: t.fixture_id, description: t.description }));

export const activeExecutionFromWire = (value: WireActiveExecution): ActiveExecution => ({
  id: value.execution_id, created_at: value.created_at, version_id: value.version_id, fixture_id: value.fixture_id,
  retrieval: retrievalFromWire(value.retrieval), execution: executionFromWire(value.execution),
  model: typeof value.config['agent_model'] === 'string' ? (value.config['agent_model'] as string) : null,
  trace_url: value.trace_url ?? null,
});
