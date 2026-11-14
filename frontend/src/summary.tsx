/**
 * The plain-language summary of a test: one lock, one sentence, one example.
 * Everything here is read from the backend's run and candidate; the lock shows a verdict and never grants approval.
 */
import type { Candidate, CaseResult, Run } from './api';
import { sideSummary } from './components';

type Tone = 'idle' | 'busy' | 'held' | 'safe' | 'unsure';

const broke = (c: CaseResult) => c.classification === 'new-policy-violation' || c.classification === 'pre-existing-violation';

export function verdictOf(candidate: Candidate | null, run: Run | null): { tone: Tone; title: string; line: string } {
  const total = run?.cases.length ?? 0;
  const broken = run ? run.cases.filter(broke).length : 0;
  const changed = run ? run.cases.filter((c) => c.classification === 'intended-safe-change').length : 0;
  const plural = (n: number) => (n === 1 ? 'request' : 'requests');
  if (!candidate) return { tone: 'idle', title: 'Not tested yet', line: 'Add a note and save the memory, then test it.' };
  if (run && (run.status === 'queued' || run.status === 'running'))
    return { tone: 'busy', title: 'Testing', line: `${run.progress.completed} of ${run.progress.total} checks done.` };
  if (candidate.state === 'approved') return { tone: 'safe', title: 'Approved and in use', line: 'The agent now uses this memory until it expires or is revoked.' };
  if (run?.admission === 'quarantine' || candidate.state === 'quarantined')
    return { tone: 'held', title: 'Quarantine', line: broken > 0
      ? `With this memory the agent breaks the refund policy in ${broken} of ${total} ${plural(total)}.`
      : 'This memory is held outside the agent and is not in use.' };
  if (run?.admission === 'eligible')
    return { tone: 'safe', title: 'Safe to approve', line: changed > 0
      ? `The agent changes its answer in ${changed} of ${total} ${plural(total)} and stays within the refund policy in all of them.`
      : `All ${total} ${plural(total)} stay within the refund policy.` };
  if (run) return { tone: 'unsure', title: 'Needs another look', line: 'The test did not give enough evidence. Test again, or open the breakdown to see why.' };
  return { tone: 'idle', title: 'Ready to test', line: 'The memory is saved but not in use. Test it to see what it would change.' };
}

function LockIcon({ open }: { open: boolean }) {
  return (
    <svg aria-hidden="true" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d={open ? 'M8 11V7.5a4 4 0 0 1 7.6-1.7' : 'M8 11V8a4 4 0 0 1 8 0v3'} />
      <path d="M12 14.5v2.5" />
    </svg>
  );
}

interface KeyPanelProps {
  candidate: Candidate | null;
  run: Run | null;
  disabled: boolean;
  onRun: () => void;
  onOpen: () => void;
}

export function KeyPanel({ candidate, run, disabled, onRun, onOpen }: KeyPanelProps) {
  const running = run ? run.status === 'queued' || run.status === 'running' : false;
  const canRun = candidate !== null && !running && ['staged', 'eligible', 'inconclusive'].includes(candidate.state);
  const v = verdictOf(candidate, run);
  return (
    <section className={`key-panel key-${v.tone}`} aria-labelledby="key-h">
      <button type="button" className="key" disabled={!run} onClick={onOpen} aria-label="Open the full breakdown">
        <LockIcon open={v.tone === 'safe'} />
      </button>
      <h2 id="key-h" className="key-verdict">{v.title}</h2>
      <p className="key-line" role="status">{v.line}</p>
      {run && running && (
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={run.progress.total} aria-valuenow={run.progress.completed} aria-label="Executions completed">
          <div style={{ width: `${run.progress.total ? (100 * run.progress.completed) / run.progress.total : 0}%` }} />
        </div>
      )}
      <div className="actions key-actions">
        {candidate && (
          <button type="button" className={run ? 'secondary' : undefined} disabled={disabled || !canRun} onClick={onRun}>
            {run ? 'Repeat this test' : 'Test this memory'}
          </button>
        )}
        {run && <button type="button" className="secondary" onClick={onOpen}>See the full breakdown</button>}
      </div>
      {run && !running && <p className="meta">Press the lock to see every request, tool call and reason.</p>}
    </section>
  );
}

/** One request, before and after: the clearest single example of what the memory does. */
export function ChangeHighlight({ run }: { run: Run | null }) {
  if (!run || run.cases.length === 0 || run.status === 'queued' || run.status === 'running') return null;
  const broken = run.cases.filter(broke);
  const changed = run.cases.filter((c) => c.classification === 'intended-safe-change');
  const unchanged = run.cases.filter((c) => c.classification === 'unchanged-safe').length;
  const pick = broken[0] ?? changed[0] ?? null;
  const bad = pick !== null && broke(pick);
  const others = (bad ? broken.length : changed.length) - 1;
  return (
    <section className="panel change" aria-labelledby="change-h">
      <h2 id="change-h">What it would change</h2>
      {pick ? (
        <>
          <p className="change-request">{pick.title}</p>
          <div className="change-grid">
            <div className="change-side">
              <span className="change-label">Agent today</span>
              <strong>{sideSummary(pick, 'baseline')}</strong>
            </div>
            <div className={`change-side ${bad ? 'change-bad' : 'change-good'}`}>
              <span className="change-label">Agent with this memory</span>
              <strong>{sideSummary(pick, 'candidate')}</strong>
              <span className="change-note">{bad ? (pick.check_reasons[0] ?? 'Breaks the refund policy') : 'Within the refund policy'}</span>
            </div>
          </div>
          <p className="meta">
            {others > 0 && `${others} more ${others === 1 ? 'request' : 'requests'} ${bad ? 'break the same way' : 'change safely'}. `}
            {unchanged > 0 && `${unchanged} ${unchanged === 1 ? 'request gets' : 'requests get'} the same answer as today.`}
          </p>
        </>
      ) : (
        <p className="change-request">Nothing changes. The agent gives the same answers with and without this memory.</p>
      )}
    </section>
  );
}
