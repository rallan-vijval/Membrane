import { ApiError } from './api/types';

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return `${err.message} Run the test again, then decide.`;
    return `${err.message} (${err.code})`;
  }
  return err instanceof Error ? err.message : 'Unexpected error';
}

export interface ArgChange {
  field: string;
  from: string;
  to: string;
}

interface Attempted {
  outcome: string;
  attempt: { arguments: Record<string, unknown> } | null;
}

const show = (value: unknown) => (value === undefined ? 'none' : typeof value === 'string' ? value : JSON.stringify(value));

/** Exact differences between two attempts: the action taken and each changed tool argument. */
export function attemptDiff(a: Attempted, b: Attempted): ArgChange[] {
  const out: ArgChange[] = [];
  if (a.outcome !== b.outcome) out.push({ field: 'action', from: a.outcome, to: b.outcome });
  const left = a.attempt?.arguments ?? {};
  const right = b.attempt?.arguments ?? {};
  if (a.attempt && b.attempt) {
    for (const key of new Set([...Object.keys(left), ...Object.keys(right)])) {
      if (JSON.stringify(left[key]) !== JSON.stringify(right[key])) out.push({ field: key, from: show(left[key]), to: show(right[key]) });
    }
  } else if (b.attempt) {
    // A refund appeared where there was none: show the arguments that make it risky or justified.
    for (const key of ['waive_return', 'exception_id']) {
      const value = right[key];
      if (value !== undefined && value !== null && value !== false) out.push({ field: key, from: 'none', to: show(value) });
    }
  }
  return out;
}
