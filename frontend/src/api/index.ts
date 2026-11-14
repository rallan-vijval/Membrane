import { httpApi } from './http';
import { syntheticApi } from './synthetic';
import type { MembraneApi } from './types';

/**
 * Synthetic mode is opt-in only: `?synthetic=1` in the URL or VITE_SYNTHETIC=1 at build time.
 * Without it the UI always talks to the real backend and shows its errors as they are.
 */
export function syntheticRequested(): boolean {
  const fromUrl = new URLSearchParams(window.location.search).get('synthetic') === '1';
  return fromUrl || import.meta.env.VITE_SYNTHETIC === '1';
}

export const api: MembraneApi = syntheticRequested() ? syntheticApi : httpApi;

export * from './types';
