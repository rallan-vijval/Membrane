import { ApiError } from './api/types';

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return `${err.message} Run the test again, then decide.`;
    return `${err.message} (${err.code})`;
  }
  return err instanceof Error ? err.message : 'Unexpected error';
}
