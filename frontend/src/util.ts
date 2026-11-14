import { ApiError, type Attempt, type Scope } from './api/types';

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return `${err.message} Refresh, run the preview again, then decide.`;
    if (err.status === 503) return `${err.message} The backend is not fully configured yet; the status lights at the top say which part.`;
    return err.code === 'network_error' ? err.message : `${err.message} (${err.code})`;
  }
  return err instanceof Error ? err.message : 'Something unexpected went wrong.';
}

export function scopeLabel(scope: Scope | undefined): string {
  if (!scope || !scope.kind || scope.kind === 'global') return 'Every order';
  if (scope.kind === 'preference') return scope.customer_id ? `Preferences of ${scope.customer_id}` : 'A customer preference';
  const parts = [`Order ${scope.order_id ?? '?'} only`];
  if (scope.customer_id) parts.push(scope.customer_id);
  if (scope.exception_id) parts.push(`exception ${scope.exception_id}`);
  return parts.join(', ');
}

export const clock = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '');

/** What the agent tried to do, in a reviewer's words. */
export function actionLabel(attempt: Attempt | null, error: string | null): string {
  if (error) return 'Run failed';
  if (!attempt) return 'No result yet';
  switch (attempt.action) {
    case 'refund_order':
      return attempt.arguments?.['waive_return'] === true ? 'Refund, return waived' : 'Refund';
    case 'request_return':
      return 'Asks for the return';
    case 'request_verification':
      return 'Asks to verify identity';
    case 'answer':
      return 'Answers, no refund';
  }
}

export interface ArgChange {
  field: string;
  from: string;
  to: string;
}

const show = (value: unknown) => (value === undefined ? 'none' : typeof value === 'string' ? value : JSON.stringify(value));

/** The exact differences between two attempts: the action and each tool argument. */
export function attemptDiff(a: Attempt | null, b: Attempt | null): ArgChange[] {
  if (!a || !b) return [];
  const out: ArgChange[] = [];
  if (a.action !== b.action) out.push({ field: 'action', from: a.action, to: b.action });
  const left = a.arguments ?? {};
  const right = b.arguments ?? {};
  if (a.action === b.action || (a.arguments && b.arguments)) {
    for (const key of new Set([...Object.keys(left), ...Object.keys(right)])) {
      if (JSON.stringify(left[key]) !== JSON.stringify(right[key])) out.push({ field: key, from: show(left[key]), to: show(right[key]) });
    }
  } else if (b.arguments) {
    for (const key of ['waive_return', 'exception_id']) {
      if (right[key] !== undefined && right[key] !== null && right[key] !== false) out.push({ field: key, from: 'none', to: show(right[key]) });
    }
  }
  return out;
}

export const num = (value: unknown): number => (typeof value === 'number' && Number.isFinite(value) ? value : 0);
