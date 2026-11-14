import type { components } from '../../api/generated';
import { ApiError } from '../../api/types';
export type DTO = components['schemas'];
export async function labRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try { response = await fetch(`/api${path}`, init); }
  catch { throw new ApiError(0, 'network_error', 'The backend is unavailable. Reload stored evidence before explicitly retrying a paid request.'); }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.error?.code ?? 'request_failed', data?.error?.message ?? 'Request failed');
  return data as T;
}
export const labPost = (body: unknown, key: string): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) });
export function rememberLabId(name: string, value: string) {
  const url = new URL(window.location.href); url.searchParams.set(name, value); window.history.replaceState(null, '', url);
}
