/**
 * PROVISIONAL adapters for the active-memory task endpoints in docs/NEXT_PHASE_PLAN.md
 * ("Contract checkpoint"): GET /api/tasks and POST /api/agent/tasks/{fixture_id}/execute.
 * Agent A has not published these in contracts/openapi.yaml yet, so nothing here is generated.
 * The plan fixes the paths and the request body; response field names below are read
 * defensively and must be replaced with generated types once the contract lands.
 */
import type { components } from './generated';
import { executionFromWire, scopeFromWire } from './normalize';
import { ApiError, type AgentHandling, type InboxTask, type MemoryUsed } from './types';

type DTO = components['schemas'];
type Loose = Record<string, unknown>;
const obj = (v: unknown): Loose => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Loose) : {});
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

export function tasksFromWire(body: unknown): InboxTask[] {
  return list(obj(body)['items']).map((raw) => {
    const item = obj(raw);
    const id = str(item['fixture_id']) ?? str(item['id']) ?? str(item['case_id']);
    return id ? { fixture_id: id, description: str(item['description']) ?? id } : null;
  }).filter((t): t is InboxTask => t !== null);
}

function memoryFromWire(raw: unknown): MemoryUsed {
  const m = obj(raw);
  const scope = m['scope'];
  const reasons = list(m['reasons']).filter((r): r is string => typeof r === 'string');
  return {
    id: str(m['memory_id']) ?? str(m['id']) ?? '',
    text: str(m['text']) ?? '',
    scope: scope && typeof scope === 'object' ? scopeFromWire(scope as DTO['Scope']) : null,
    reason: str(m['reason']) ?? (reasons.length ? reasons.join(', ') : null),
    score: typeof m['semantic_score'] === 'number' ? (m['semantic_score'] as number) : typeof m['score'] === 'number' ? (m['score'] as number) : null,
  };
}

export function handlingFromWire(body: unknown): AgentHandling {
  const b = obj(body);
  const execution = b['execution'] ?? b['result'];
  if (!execution || typeof execution !== 'object') {
    throw new ApiError(502, 'unexpected_shape', 'The backend answered, but not in the shape this screen expects yet. The task endpoint contract is still provisional.');
  }
  const retrieval = obj(b['memory_retrieval'] ?? b['retrieval']);
  return {
    execution_id: str(b['execution_id']) ?? '',
    version_id: str(b['version_id']) ?? str(b['base_version_id']) ?? '',
    // The plan says the result is "Execution-shaped"; side/repetition may be absent for a single live run.
    execution: executionFromWire({ side: 'baseline', repetition: 1, raw_responses: [], checks: [], error: null, input_hash: '', calls: 0,
      input_tokens: 0, output_tokens: 0, latency_ms: 0, attempt: null, tool_outcome: null, ...(execution as Loose) } as DTO['Execution']),
    memories_used: list(retrieval['entries'] ?? b['entries']).map(memoryFromWire),
    trace_url: str(b['trace_url']),
  };
}
