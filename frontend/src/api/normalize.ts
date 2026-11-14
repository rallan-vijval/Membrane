/** Explicit, typed wire-to-view adapters. Never synthesize provider evidence here. */
import type { components } from './generated';
import type { ActiveMemory, Candidate, Execution, Health, History, Run, Scope, SelectionReason, Source } from './types';

type DTO = components['schemas'];
const number = (obj: Record<string, unknown>, key: string) => typeof obj[key] === 'number' ? obj[key] as number : 0;
const string = (obj: Record<string, unknown>, key: string) => typeof obj[key] === 'string' ? obj[key] as string : null;

export function scopeFromWire(scope: DTO['Scope']): Scope {
  return scope.kind === 'order'
    ? { kind: 'order', order_id: scope.order_id ?? '', customer_id: scope.customer_id ?? null, exception_id: scope.exception_id ?? null }
    : { kind: scope.kind ?? 'global' };
}

export const healthFromWire = (value: DTO['Health']): Health => ({
  database: { status: value.database.status, detail: value.database.reason },
  model: { status: value.model.status, detail: value.model.reason },
  search: { status: value.search.status, detail: value.search.reason },
  voice: { status: value.voice.status, detail: value.voice.reason },
});

export const sourceFromWire = (value: DTO['Source']): Source => ({
  id: value.source_id, extracted_text: value.extracted_text, quotation: value.quotation,
  proposed_candidate: { text: value.proposed_text, scope: scopeFromWire(value.proposed_scope) },
  provenance: { sha256: value.sha256, mime_type: value.mime_type,
    extraction_model: string(value.provenance, 'model'), trusted: false },
  image_url: value.image_url, created_at: value.created_at,
});

export const candidateFromWire = (value: DTO['Candidate']): Candidate => ({
  id: value.candidate_id, source_id: value.source_id, text: value.text, scope: scopeFromWire(value.scope),
  state: value.status, parent_candidate_id: value.parent_candidate_id, base_version_id: value.base_version_id,
  content_hash: value.content_hash, latest_run_id: value.latest_run_id ?? null, created_at: value.created_at,
});

function executionFromWire(value: DTO['Execution']): Execution {
  const attempt = value.attempt;
  const outcome = value.tool_outcome;
  return { side: value.side, repetition: value.repetition,
    outcome: value.error ? 'error' : attempt?.action === 'refund_order' ? 'refund' : attempt?.action ?? 'error',
    answer_text: attempt?.answer ?? '',
    attempt: attempt?.action === 'refund_order' ? { tool: 'refund_order', arguments: attempt.arguments ?? {} } : null,
    enforcement: outcome ? { allowed: outcome.allowed === true,
      reasons: Array.isArray(outcome.reasons) ? outcome.reasons.filter((r): r is string => typeof r === 'string') : [] } : null,
    error: value.error, raw_responses: value.raw_responses, checks: value.checks,
  };
}

const selectionReason = (reasons: string[]): SelectionReason => reasons.includes('mandatory_policy_sentinel') ? 'sentinel'
  : reasons.includes('atlas_vector_search') ? 'vector' : reasons.includes('deterministic_scope_neighbor') ? 'neighbor' : 'fill';

export function runFromWire(value: DTO['Run']): Run {
  const selected = new Map(value.selection.map((s) => [s.case_id, s]));
  return {
    id: value.run_id, candidate_id: value.candidate_id, status: value.status, admission: value.admission,
    progress: value.progress as { completed: number; total: number },
    selection: value.selection.map((s) => ({ fixture_id: s.case_id, title: s.description,
      reason: selectionReason(s.reasons), reasons: s.reasons, score: s.semantic_score })),
    cases: value.cases.map((c) => ({ case_id: c.case_id, fixture_id: c.case_id,
      title: selected.get(c.case_id)?.description ?? c.case_id,
      classification: c.executions.length === 0 ? null : c.classification,
      check_reasons: [...new Set(c.executions.flatMap((e) => e.checks.map((check) => `${check.passed ? '✓' : '✕'} ${check.code}: ${check.reason}`)))],
      executions: c.executions.map(executionFromWire),
    })),
    reasons: value.reasons,
    errors: [...new Set(value.cases.flatMap((c) => c.executions.filter((e) => e.error).map((e) => `${c.case_id} / ${e.side} / repetition ${e.repetition}: ${e.error}`)))],
    model_config: { provider: string(value.config, 'provider') ?? 'unknown', agent_model: string(value.config, 'agent_model') ?? 'unknown',
      temperature: typeof value.config.temperature === 'number' ? value.config.temperature : null },
    usage: { model_calls: number(value.usage, 'model_calls'), input_tokens: number(value.summary, 'input_tokens'),
      output_tokens: number(value.summary, 'output_tokens'), latency_ms: number(value.usage, 'elapsed_ms') || number(value.summary, 'latency_ms') },
    recorded: value.live === false, created_at: value.created_at, completed_at: null,
  };
}

export const activeFromWire = (value: DTO['Version']): ActiveMemory => ({
  version_id: value.version_id, revision: null, activated_at: value.created_at,
  entries: value.memories.map((m, index) => ({ id: `${value.version_id}:${index}`, text: string(m, 'text') ?? '',
    scope: scopeFromWire((m.scope ?? { kind: 'global' }) as DTO['Scope']), candidate_id: string(m, 'candidate_id') })),
});

export const historyFromWire = (value: DTO['History']): History => ({
  versions: value.versions.map((v) => ({ version_id: v.version_id, parent_version_id: v.parent_version_id,
    candidate_id: v.candidate_id ?? null, run_id: v.run_id ?? null, activated_at: v.created_at })),
  events: value.events.map((e) => ({ id: e.event_id, decision: e.decision as 'approve' | 'quarantine' | 'revise',
    actor: e.actor, candidate_id: e.candidate_id, run_id: e.run_id, version_id: e.version_id, reason: e.reason, created_at: e.created_at })),
  truncated: value.truncated,
});
