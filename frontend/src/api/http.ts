import {
  ApiError,
  type ApiErrorBody,
  type MembraneApi,
  type Repetition,
  type Scope,
  type Side,
} from './types';

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

const json = (body: unknown, idempotent = false): RequestInit => ({
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    // Reviewer actions must be safe to retry: one key per click.
    ...(idempotent ? { 'Idempotency-Key': crypto.randomUUID() } : {}),
  },
  body: JSON.stringify(body),
});

const id = (value: string) => encodeURIComponent(value);

/** The real backend. It never substitutes synthetic data: failures surface as errors. */
export const httpApi: MembraneApi = {
  mode: 'real',
  health: () => request('/health'),
  uploadSource: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request('/sources', { method: 'POST', body: form });
  },
  getSource: (sourceId: string) => request(`/sources/${id(sourceId)}`),
  createCandidate: (input) => request('/candidates', json(input)),
  getCandidate: (candidateId: string) => request(`/candidates/${id(candidateId)}`),
  startRun: (candidateId: string) => request(`/candidates/${id(candidateId)}/runs`, json({})),
  getRun: (runId: string) => request(`/runs/${id(runId)}`),
  revise: (candidateId: string, input: { text: string; scope: Scope }) =>
    request(`/candidates/${id(candidateId)}/revise`, json(input, true)),
  approve: (candidateId: string, runId: string) =>
    request(`/candidates/${id(candidateId)}/approve`, json({ run_id: runId }, true)),
  quarantine: (candidateId: string, reason: string) =>
    request(`/candidates/${id(candidateId)}/quarantine`, json({ reason }, true)),
  activeMemory: () => request('/memory/active'),
  history: () => request('/history'),
  audio: (runId: string, caseId: string, side: Side, repetition: Repetition) =>
    request(`/runs/${id(runId)}/cases/${id(caseId)}/audio`, json({ side, repetition })),
};
