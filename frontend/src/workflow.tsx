import type { Candidate, Run, Source } from './api';

/** A presentation of persisted state, never an alternative approval gate. */
export function WorkflowGuide({ source, candidate, run }: { source: Source | null; candidate: Candidate | null; run: Run | null }) {
  const approved = candidate?.state === 'approved';
  const running = run?.status === 'running' || run?.status === 'queued';
  const stage = approved ? 3 : run ? (running ? 1 : 2) : candidate ? 1 : 0;
  const steps = ['Propose a memory', 'Test it', 'Inspect what changed', 'Approve or reject'];
  const next = approved ? 'This revision is approved. Inspect active memory, then try the current agent.'
    : running ? `The experiment is running: ${run.progress.completed} of ${run.progress.total} decisions recorded.`
    : run ? (run.admission === 'eligible' ? 'Evidence is eligible. Review it before approving this exact revision.' : 'This memory cannot be approved. Inspect the failures, edit the proposal and test again.')
    : candidate ? 'Run the behavior test. The proposed memory is still isolated.'
    : source ? 'Review the extracted text, scope and lifetime, then save it for testing.'
    : 'Upload a note or PDF. We will extract a proposed memory for you to review.';
  return <section className="workflow-guide" aria-label="Review workflow">
    <ol className="journey">{steps.map((label, i) => <li key={label} className={i === stage ? 'journey-current' : i < stage ? 'journey-done' : ''} aria-current={i === stage ? 'step' : undefined}><span aria-hidden="true">{i < stage ? '✓' : String(i + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
    <p className="next-step" role="status"><strong>Next</strong> {next}<span className="boundary-label">{approved ? '✓ Approved' : '◇ Not in use yet'}</span></p>
  </section>;
}

export function ExperimentSummary({ run }: { run: Run | null }) {
  if (!run) return null;
  const count = (kind: string) => run.cases.filter(c => c.classification === kind).length;
  const outcomes = [
    { label: 'New violations', value: count('new-policy-violation'), tone: 'failure', symbol: '×' },
    { label: 'Baseline violations', value: count('pre-existing-violation'), tone: 'failure', symbol: '↶' },
    { label: 'Inconclusive', value: count('inconclusive'), tone: 'uncertain', symbol: '?' },
    { label: 'Safe changes', value: count('intended-safe-change'), tone: 'safe', symbol: '✓' },
    { label: 'Safe, unchanged', value: count('unchanged-safe'), tone: 'neutral', symbol: '=' },
  ];
  return <div className="experiment-summary" aria-label="Recorded case outcomes">
    <div className="experiment-key"><span>A <small>Without the proposed memory</small></span><span className="experiment-boundary">MEMBRANE</span><span>B <small>With the proposed memory</small></span></div>
    <div className="outcome-strip">{outcomes.filter(o => o.value > 0).map(o => <div className={`outcome outcome-${o.tone}`} key={o.label}><span aria-hidden="true">{o.symbol}</span><strong>{o.value}</strong><span>{o.label}</span></div>)}</div>
  </div>;
}
