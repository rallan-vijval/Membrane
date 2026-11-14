import type { Candidate, Run, Source } from './api';

/** A presentation of persisted state, never an alternative approval gate. */
export function WorkflowGuide({ source, candidate, run }: { source: Source | null; candidate: Candidate | null; run: Run | null }) {
  const approved = candidate?.state === 'approved';
  const running = run?.status === 'running' || run?.status === 'queued';
  const stage = approved ? 4 : run ? (running ? 2 : 3) : candidate ? 2 : source ? 1 : 0;
  const steps = ['Read the source', 'Shape the memory', 'Compare behavior', 'Review the evidence', 'Activate deliberately'];
  const next = approved ? 'This revision is approved. Inspect active memory, then try the current agent.'
    : running ? `The experiment is running: ${run.progress.completed} of ${run.progress.total} decisions recorded.`
    : run ? (run.admission === 'eligible' ? 'Evidence is eligible. Review it before approving this exact revision.' : 'Admission is blocked. Inspect the evidence, revise the candidate and test again.')
    : candidate ? 'Run the behavior test. The proposed memory is still isolated.'
    : source ? 'Review the extracted text, scope and lifetime, then stage a candidate.'
    : 'Upload a note or PDF. We will extract a proposed memory for you to review.';
  return <section className="workflow-guide" aria-label="Review workflow">
    <div className="workflow-intro"><div><p className="eyebrow">THE MEMORY CHECKPOINT</p><h2>Before it becomes a habit.</h2><p>See what a proposed memory changes before the live agent can use it.</p></div><span className="boundary-label">{approved ? '✓ Revision approved' : '◇ Proposed memory stays isolated'}</span></div>
    <ol className="journey">{steps.map((label, i) => <li key={label} className={i === stage ? 'journey-current' : i < stage ? 'journey-done' : ''} aria-current={i === stage ? 'step' : undefined}><span aria-hidden="true">{i < stage ? '✓' : String(i + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
    <p className="next-step" role="status"><strong>Next step</strong> {next}</p>
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
    <div className="experiment-key"><span>A <small>Current memory</small></span><span className="experiment-boundary">MEMBRANE</span><span>B <small>Current + proposed</small></span></div>
    <div className="outcome-strip">{outcomes.map(o => <div className={`outcome outcome-${o.tone}`} key={o.label}><span aria-hidden="true">{o.symbol}</span><strong>{o.value}</strong><span>{o.label}</span></div>)}</div>
    <p className="meta">Recorded cases only. Inconclusive means missing, invalid or unmet evidence; it is not proof of a new violation. Open a case below to inspect the actual actions and checks.</p>
  </div>;
}
