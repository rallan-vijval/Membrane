import { ApiError, type ErrorResponse, type MembraneApi, type Repetition, type Scope, type Side } from './types';

/** Empty by default: the dev proxy (or a host rewrite rule) serves /api from the same origin. */
const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '');

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, init);
  } catch {
    throw new ApiError(0, 'network_error', 'The Membrane backend is not reachable. Start it, or check the API address.');
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ErrorResponse | null)?.error;
    throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `Request failed (${res.status})`, err?.details ?? null);
  }
  return body as T;
}

/** Reviewer decisions carry a fresh Idempotency-Key per click, as the contract requires. */
const post = (body?: unknown, idempotent = false): RequestInit => ({
  method: 'POST',
  headers: {
    ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    ...(idempotent ? { 'Idempotency-Key': crypto.randomUUID() } : {}),
  },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

const seg = (value: string) => encodeURIComponent(value);

/** The real backend. It never substitutes synthetic data: failures surface as errors. */
export const httpApi: MembraneApi = {
  mode: 'real',
  asset: (url: string) => (/^(https?:|blob:|data:)/.test(url) ? url : `${BASE}${url}`),
  health: () => request('/health'),
  uploadSource: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request('/sources', { method: 'POST', body: form });
  },
  getSource: (sourceId: string) => request(`/sources/${seg(sourceId)}`),
  listCandidates: () => request('/candidates'),
  createCandidate: (input) => request('/candidates', post(input)),
  getCandidate: (candidateId: string) => request(`/candidates/${seg(candidateId)}`),
  startRun: (candidateId: string) => request(`/candidates/${seg(candidateId)}/runs`, post()),
  getRun: (runId: string) => request(`/runs/${seg(runId)}`),
  revise: (candidateId: string, input: { text: string; scope: Scope }) => request(`/candidates/${seg(candidateId)}/revise`, post(input)),
  approve: (candidateId: string, input: { run_id: string; reason: string }) =>
    request(`/candidates/${seg(candidateId)}/approve`, post(input, true)),
  quarantine: (candidateId: string, reason: string) => request(`/candidates/${seg(candidateId)}/quarantine`, post({ reason }, true)),
  activeMemory: () => request('/memory/active'),
  history: () => request('/history'),
  audio: (runId: string, caseId: string, side: Side, repetition: Repetition) =>
    request(`/runs/${seg(runId)}/cases/${seg(caseId)}/audio`, post({ side, repetition })),
};
