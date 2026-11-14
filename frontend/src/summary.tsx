/** Security verdicts use persisted test state and current backend membership, never grant authority. */
import type { Candidate, CaseResult, Run } from './api';
import { sideSummary } from './components';

type Tone = 'idle' | 'busy' | 'held' | 'safe' | 'unsure';
export function verdictOf(candidate: Candidate | null, run: Run | null, inUse: boolean | null = null): { tone: Tone; title: string; line: string } {
  if (!candidate) return { tone: 'idle', title: 'Memory vault locked', line: 'Add a source to begin. Nothing enters memory without approval.' };
  if (candidate.state === 'approved') return inUse === true
    ? { tone: 'safe', title: 'Memory in use', line: 'This memory is active in the current backend snapshot.' }
    : inUse === false ? { tone: 'idle', title: 'No longer in use', line: 'Previously approved; now withdrawn, expired or outside the active version.' }
      : { tone: 'unsure', title: 'Approval recorded', line: 'Current memory availability could not be verified.' };
  if (run && (run.candidate_id !== candidate.id || candidate.latest_run_id !== run.id))
    return { tone: 'unsure', title: 'Different revision', line: 'Run a test for this exact saved memory.' };
  if (run && ['queued', 'running'].includes(run.status))
    return { tone: 'busy', title: 'Inspecting memory', line: `${run.progress.completed} of ${run.progress.total} decisions recorded.` };
  const added = run?.cases.filter(c => c.classification === 'new-policy-violation').length ?? 0;
  const existing = run?.cases.filter(c => c.classification === 'pre-existing-violation').length ?? 0;
  if (run?.admission === 'quarantine' || candidate.state === 'quarantined')
    return { tone: 'held', title: 'Quarantined', line: added ? `${added} request${added === 1 ? '' : 's'} failed with the proposed memory.${existing ? ` ${existing} already failed without it.` : ''}`
      : existing ? `${existing} request${existing === 1 ? '' : 's'} already failed without this memory. Approval is blocked.` : 'This memory is held outside the live agent.' };
  if (run?.status === 'completed' && run.admission === 'eligible' && candidate.state === 'eligible')
    return { tone: 'safe', title: 'Passed checks', line: 'Still isolated. Your approval is required before use.' };
  if (run) return { tone: 'unsure', title: 'Needs investigation', line: 'The test did not establish enough passing evidence.' };
  return { tone: 'idle', title: 'Ready for inspection', line: 'Isolated until tested and approved.' };
}

export function LockIcon({ open = false, small = false }: { open?: boolean; small?: boolean }) {
  return <svg aria-hidden="true" width={small ? 24 : 64} height={small ? 24 : 64} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="11" width="14" height="9" rx="2" /><path d={open ? 'M8 11V7.5a4 4 0 0 1 7.6-1.7' : 'M8 11V8a4 4 0 0 1 8 0v3'} /><path d="M12 14.5v2.5" /></svg>;
}

export function KeyPanel({ candidate, run, hasSource = false, inUse, disabled, onRun, onOpen }: { candidate: Candidate | null; run: Run | null; hasSource?: boolean; inUse: boolean | null; disabled: boolean; onRun: () => void; onOpen: () => void }) {
  const running = !!run && ['queued', 'running'].includes(run.status);
  const canRun = candidate !== null && !running && ['staged', 'eligible', 'inconclusive'].includes(candidate.state);
  const verdict = !candidate && hasSource ? { tone: 'idle', title: 'Review memory', line: 'Check the proposal below, then save it for testing.' } : verdictOf(candidate, run, inUse);
  return <section className={`key-panel key-${verdict.tone}`} aria-labelledby="key-h">
    <button type="button" className="key" disabled={!run} onClick={onOpen} aria-label="Inspect security verdict"><LockIcon open={inUse === true} /></button>
    <h2 id="key-h" className="key-verdict">{verdict.title}</h2><p className="key-line" role="status">{verdict.line}</p>
    {run?.recorded && <span className="tag">Recorded evidence</span>}
    {run && running && <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={run.progress.total} aria-valuenow={run.progress.completed} aria-label="Test decisions recorded"><div style={{ width: `${run.progress.total ? Math.min(100, 100 * run.progress.completed / run.progress.total) : 0}%` }} /></div>}
    <div className="actions key-actions">{candidate && canRun && candidate.state !== 'eligible' && <button type="button" className={run ? 'secondary' : undefined} disabled={disabled || !canRun} onClick={onRun}>{run ? 'Repeat this test' : 'Test this memory'}</button>}{run && <button type="button" className="secondary" onClick={onOpen}>Open detailed results</button>}</div>
  </section>;
}

export function ChangeHighlight({ run }: { run: Run | null }) {
  if (!run || run.cases.length === 0 || ['queued', 'running'].includes(run.status)) return null;
  const added = run.cases.filter(c => c.classification === 'new-policy-violation');
  const existing = run.cases.filter(c => c.classification === 'pre-existing-violation');
  const changed = run.cases.filter(c => c.classification === 'intended-safe-change');
  const pick: CaseResult | undefined = added[0] ?? existing[0] ?? changed[0];
  const inconclusive = run.cases.some(c => c.classification === 'inconclusive' || c.classification === null);
  const failed = pick?.executions.flatMap(e => e.checks?.filter(c => !c.passed).map(c => c.reason) ?? [])[0];
  return <section className="panel change" aria-labelledby="change-h"><h2 id="change-h">{added.length ? 'A boundary was crossed' : existing.length ? 'An existing problem' : 'What changed?'}</h2>
    {pick ? <><p className="change-request">{pick.title}</p><div className="change-grid"><div className="change-side"><span className="change-label">Without this memory</span><strong>{sideSummary(pick, 'baseline')}</strong></div><div className={`change-side ${added.length || existing.length ? 'change-bad' : 'change-good'}`}><span className="change-label">With this memory</span><strong>{sideSummary(pick, 'candidate')}</strong><span className="change-note">{failed ?? 'The recorded checks passed.'}</span></div></div>{existing.length > 0 && added.length === 0 && <p className="meta">The baseline already failed; this is not evidence that the proposed memory caused the problem.</p>}</>
      : <p className="change-request">{inconclusive ? 'Some responses could not be checked. Inspect the evidence.' : 'No action changed in these recorded requests.'}</p>}
  </section>;
}
