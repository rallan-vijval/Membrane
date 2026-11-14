import type { Candidate, Run, Source } from './api';

export function UseProgress({ source, candidate, run }: { source: Source | null; candidate: Candidate | null; run: Run | null }) {
  const stage = run && !['queued', 'running'].includes(run.status) ? 3 : candidate ? 2 : source ? 1 : 0;
  return <ol className="use-progress" aria-label="Simple workflow">{['Upload / record', 'Review memory', 'Test behavior', 'Decide'].map((label, i) => <li key={label} aria-current={i === stage ? 'step' : undefined}><span aria-hidden="true">{i < stage ? '✓' : i + 1}</span>{label}</li>)}</ol>;
}

export function QuickTest({ candidate, run, disabled, onRun, onDetails }: { candidate: Candidate | null; run: Run | null; disabled: boolean; onRun: () => void; onDetails: () => void }) {
  if (!candidate) return null;
  const running = !!run && ['queued', 'running'].includes(run.status);
  const canRun = !disabled && !running && ['staged', 'eligible', 'inconclusive'].includes(candidate.state);
  const completed = run?.progress.completed ?? 0;
  const total = run?.progress.total ?? 0;
  const ratio = total > 0 ? Math.min(1, Math.max(0, completed / total)) : 0;
  return <section className="panel quick-test" aria-labelledby="quick-test-h">
    <div><h2 id="quick-test-h">Test the proposed memory</h2><div className="quick-comparison" aria-label="Compare without and with this memory"><span><strong>A</strong> Without it</span><span aria-hidden="true">⇄</span><span><strong>B</strong> With it</span></div>
    <div className="actions"><button type="button" disabled={!canRun} onClick={onRun}>{run ? 'Repeat this test' : 'Test this memory'}</button>{run && <button type="button" className="secondary" onClick={onDetails}>Open detailed results</button>}</div>
    <p className="meta">Testing keeps this proposal isolated. Approval is a separate action.</p></div>
    {run && <div className="decision-progress" role="progressbar" aria-label="Test decisions recorded" aria-valuemin={0} aria-valuemax={total} aria-valuenow={completed}>
      <svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="48" className="ring-track" /><circle cx="60" cy="60" r="48" className="ring-value" strokeDasharray={`${ratio * 301.593} 301.593`} /></svg>
      <span><strong>{completed}/{total}</strong><small>{running ? 'running' : run.status}</small></span>
    </div>}
  </section>;
}
