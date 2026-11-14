import {
  ApiError,
  type ApiErrorBody,
  type MembraneApi,
  type Repetition,
  type Scope,
  type Side,
} from './types';
import type { components } from './generated';
import { handlingFromWire, tasksFromWire } from './inboxWire';
import { activeFromWire, candidateFromWire, healthFromWire, historyFromWire, runFromWire, sourceFromWire } from './normalize';
type DTO = components['schemas'];

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError(0, 'network_error', 'The backend is not reachable at /api.');
  }
  if (res.status === 204) return undefined as T;
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `Request failed (${res.status})`, err?.details ?? null);
  }
  return body as T;
}

const reviewerKeys = new Map<string, string>();
const reviewerKey = (identity: string) => {
  if (!reviewerKeys.has(identity)) reviewerKeys.set(identity, crypto.randomUUID());
  return reviewerKeys.get(identity)!;
};
const json = (body: unknown, reviewIdentity?: string): RequestInit => ({
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    // Retrying the same decision after a network failure reuses its key.
    ...(reviewIdentity ? { 'Idempotency-Key': reviewerKey(reviewIdentity) } : {}),
  },
  body: JSON.stringify(body),
});

const id = (value: string) => encodeURIComponent(value);

/** The real backend. It never substitutes synthetic data: failures surface as errors. */
export const httpApi: MembraneApi = {
  mode: 'real',
  health: () => request<DTO['Health']>('/health').then(healthFromWire),
  uploadSource: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<DTO['Source']>('/sources', { method: 'POST', body: form }).then(sourceFromWire);
  },
  getSource: (sourceId: string) => request<DTO['Source']>(`/sources/${id(sourceId)}`).then(sourceFromWire),
  createCandidate: (input) => request<DTO['Candidate']>('/candidates', json(input)).then(candidateFromWire),
  getCandidate: (candidateId: string) => request<DTO['Candidate']>(`/candidates/${id(candidateId)}`).then(candidateFromWire),
  startRun: (candidateId: string) => request(`/candidates/${id(candidateId)}/runs`, json({})),
  getRun: (runId: string) => request<DTO['Run']>(`/runs/${id(runId)}`).then(runFromWire),
  revise: (candidateId: string, input: { text: string; scope: Scope }) =>
    request<DTO['Candidate']>(`/candidates/${id(candidateId)}/revise`, json(input)).then(candidateFromWire),
  approve: (candidateId: string, runId: string) =>
    request<DTO['Candidate']>(`/candidates/${id(candidateId)}/approve`, json({ run_id: runId,
      reason: 'Reviewer approved the exact candidate after reviewing paired evidence' }, `approve:${candidateId}:${runId}`)).then(candidateFromWire),
  quarantine: (candidateId: string, reason: string) =>
    request<DTO['Candidate']>(`/candidates/${id(candidateId)}/quarantine`, json({ reason }, `quarantine:${candidateId}:${reason}`)).then(candidateFromWire),
  activeMemory: () => request<DTO['Version']>('/memory/active').then(activeFromWire),
  history: () => request<DTO['History']>('/history').then(historyFromWire),
  audio: (runId: string, caseId: string, side: Side, repetition: Repetition) =>
    request(`/runs/${id(runId)}/cases/${id(caseId)}/audio`, json({ side, repetition })),
  // Planned in docs/NEXT_PHASE_PLAN.md; a 404 here means the backend has not shipped them yet.
  listTasks: () => request<unknown>('/tasks').then(tasksFromWire),
  executeTask: (fixtureId: string, baseVersionId: string) =>
    request<unknown>(`/agent/tasks/${id(fixtureId)}/execute`, json({ base_version_id: baseVersionId })).then(handlingFromWire),
};
