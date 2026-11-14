/** Canonical active-task DTOs mapped to inbox view models; no provisional aliases. */
import type { components } from './generated';
import { executionFromWire, scopeFromWire } from './normalize';
import type { AgentHandling, InboxTask } from './types';

type DTO = components['schemas'];

export const tasksFromWire = (body: DTO['TaskOptions']): InboxTask[] => body.items.map((item) => ({
  fixture_id: item.fixture_id, description: item.description,
}));

export const handlingFromWire = (body: DTO['ActiveExecution']): AgentHandling => ({
  execution_id: body.execution_id,
  version_id: body.version_id,
  execution: executionFromWire(body.execution),
  memories_used: body.retrieval.entries.map((memory) => ({
    id: memory.memory_id, text: memory.text, scope: scopeFromWire(memory.scope),
    reason: memory.reason, score: memory.semantic_score,
  })),
  trace_url: body.trace_url ?? null,
});
