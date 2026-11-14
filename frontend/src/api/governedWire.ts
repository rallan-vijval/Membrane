import type { components } from './generated';
import { executionFromWire, scopeFromWire } from './normalize';
import type { ActiveExecution, CaseRetrieval, GovernedEntry, GovernedMemory, RetrievedMemory, TaskOption } from './types';

type DTO = components['schemas'];

export type WireMemoryEntry = Omit<DTO["MemoryEntries"]["items"][number], "availability"> & { availability?: "active" | "expired" };
export type WireMemoryEntries = DTO["MemoryEntries"];
export type WireRetrievedMemory = DTO["RetrievedMemory"];
export type WireMemoryRetrieval = DTO["MemoryRetrieval"];
export type WireTaskOptions = DTO["TaskOptions"];
export type WireActiveExecution = DTO["ActiveExecution"];
export type WireRevokeResult = DTO["RevokeResult"];

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
