import { useEffect, useState, type ReactNode } from 'react';
import { api, type Candidate, type CaseResult, type Classification, type Execution, type GovernedMemory, type Health, type History, type Run } from './api';
import { ExecutionDetail } from './components';
import { describeError } from './util';

export type DashboardPanel = 'overview' | 'evidence' | 'experiments' | 'memory';
const OUTCOMES: { id: Classification; label: string; tone: string }[] = [
  { id: 'new-policy-violation', label: 'New violations', tone: 'failure' },
  { id: 'pre-existing-violation', label: 'Baseline violations', tone: 'failure' },
  { id: 'inconclusive', label: 'Inconclusive', tone: 'uncertain' },
  { id: 'intended-safe-change', label: 'Safe changes', tone: 'safe' },
  { id: 'unchanged-safe', label: 'Safe, unchanged', tone: 'neutral' },
];
const CANDIDATE_STATES = ['staged', 'testing', 'eligible', 'quarantined', 'inconclusive', 'approved'] as const;
const stateLabel = (state: string) => ({ staged: 'Saved', testing: 'Testing', eligible: 'Passed checks', quarantined: 'Rejected', inconclusive: 'Inconclusive', approved: 'Approved' })[state] ?? state;

function HorizontalBar({ label, value, total, tone = 'neutral', pressed, onClick }: { label: string; value: number; total: number; tone?: string; pressed?: boolean; onClick: () => void }) {
  return <button type="button" className={`chart-row tone-${tone}`} aria-label={`${label}: ${value}`} aria-pressed={pressed} onClick={onClick}>
    <span>{label}</span><span className="chart-track" aria-hidden="true"><span style={{ width: `${total ? Math.min(100, value / total * 100) : 0}%` }} /></span><strong>{value}</strong>
  </button>;
}
function decisionStatus(execution: Execution | undefined) {
  if (!execution) return { symbol: '·', text: 'Pending', tone: 'pending' };
  if (execution.error) return { symbol: '!', text: 'Invalid response', tone: 'uncertain' };
  if (!execution.checks?.length) return { symbol: '?', text: 'No checks', tone: 'uncertain' };
  if (execution.checks.some(check => !check.passed)) return { symbol: '×', text: 'Failed check', tone: 'failure' };
  return { symbol: '✓', text: 'Passed checks', tone: 'safe' };
}

interface Props {
  visible: boolean; panel: DashboardPanel; onPanel: (panel: DashboardPanel) => void;
  candidate: Candidate | null; run: Run | null; history: History | null; memory: GovernedMemory | null; health: Health | null;
  onSelectCandidate: (id: string) => void; onUse: () => void;
  evidence: ReactNode; experiments: ReactNode; memoryTools: ReactNode;
}
export function Dashboard({ visible, panel, onPanel, candidate, run, history, memory, health, onSelectCandidate, onUse, evidence, experiments, memoryTools }: Props) {
  const [saved, setSaved] = useState<{ items: Candidate[]; truncated: boolean } | null>(null);
  const [savedProblem, setSavedProblem] = useState<string | null>(null);
  const [candidateFilter, setCandidateFilter] = useState<string | null>(null);
  const [outcomeFilter, setOutcomeFilter] = useState<Classification | null>(null);
  const [selected, setSelected] = useState<{ caseId: string; side: 'baseline' | 'candidate'; repetition: 1 | 2 } | null>(null);
  const [eventFilter, setEventFilter] = useState<string | null>(null);
  useEffect(() => {
    if (!visible) return;
    let alive = true;
    api.listCandidates().then(value => { if (alive) { setSaved(value); setSavedProblem(null); } })
      .catch(err => { if (alive) { setSaved(null); setSavedProblem(describeError(err)); } });
    return () => { alive = false; };
  }, [visible, candidate?.id, candidate?.state]);
  useEffect(() => { setSelected(null); setOutcomeFilter(null); }, [run?.id]);
  useEffect(() => { setSelected(null); }, [outcomeFilter]);
  const rows = run?.cases.filter(c => !outcomeFilter || c.classification === outcomeFilter) ?? [];
  const selectedCase: CaseResult | undefined = run?.cases.find(c => c.case_id === selected?.caseId);
  const selectedExecution = selectedCase?.executions.find(e => e.side === selected?.side && e.repetition === selected.repetition);
  const choices = saved?.items.filter(c => !candidateFilter || c.state === candidateFilter) ?? [];
  const candidateOptions = candidate && !choices.some(c => c.id === candidate.id) ? [candidate, ...choices] : choices;
  const activeCount = memory?.items.filter(m => m.availability === 'active').length ?? 0;
  const expiredCount = memory?.items.filter(m => m.availability === 'expired').length ?? 0;
  const events = history?.events.filter(e => !eventFilter || e.decision === eventFilter) ?? [];
  return <main className="dashboard-shell" hidden={!visible} aria-label="Detailed dashboard">
    <div className="dashboard-heading"><div><h2>Dashboard</h2><p className="meta">Saved evidence and observed results. Opening this page never runs a model.</p></div><button type="button" className="secondary" onClick={onUse}>Back to upload and test</button></div>
    <nav className="dashboard-tabs" aria-label="Dashboard sections">{(['overview', 'evidence', 'experiments', 'memory'] as const).map(tab => <button type="button" className="secondary" key={tab} aria-pressed={panel === tab} onClick={() => onPanel(tab)}>{{ overview: 'Overview', evidence: 'Test evidence', experiments: 'Scope experiments', memory: 'Approved memory' }[tab]}</button>)}</nav>
    <section className="dashboard-source panel" aria-label="Select saved evidence"><label className="field"><span>Saved proposal</span><select aria-label="Saved proposal" value={candidate?.id ?? ''} onChange={event => { if (event.target.value) onSelectCandidate(event.target.value); }}><option value="">Select a saved proposal</option>{candidateOptions.map(c => <option key={c.id} value={c.id}>{stateLabel(c.state)} · {c.text.slice(0, 90)}</option>)}</select></label>{savedProblem && <p role="status" className="dashboard-status">Saved proposals unavailable: {savedProblem}</p>}<p className="meta">{run ? `Selected admission run: ${run.id}${run.recorded ? ' · recorded evidence' : ''}` : 'Select a proposal with a saved test to inspect its results.'}</p></section>
    <div hidden={panel !== 'overview'} className="dashboard-overview">
      <section className="panel outcome-chart" aria-labelledby="outcome-chart-h"><h3 id="outcome-chart-h">Admission outcomes</h3>
        {!run ? <p className="empty">No admission run selected.</p> : <><p className="meta">This run only · {run.cases.filter(c => c.classification !== null).length} classified requests · {run.progress.completed}/{run.progress.total} decisions recorded</p><div className="bar-chart">{OUTCOMES.map(o => <HorizontalBar key={o.id} label={o.label} value={run.cases.filter(c => c.classification === o.id).length} total={run.cases.length} tone={o.tone} pressed={outcomeFilter === o.id} onClick={() => setOutcomeFilter(old => old === o.id ? null : o.id)} />)}</div>{outcomeFilter && <button type="button" className="link" onClick={() => setOutcomeFilter(null)}>Show all requests</button>}</>}
      </section>
      <section className="panel" aria-labelledby="usage-h"><h3 id="usage-h">Selected run usage</h3>{run ? <dl className="usage-grid"><div><dt>Model calls</dt><dd>{run.usage.reported?.model_calls === false ? 'Not reported' : run.usage.model_calls.toLocaleString()}</dd></div><div><dt>Input tokens</dt><dd>{run.usage.reported?.input_tokens === false ? 'Not reported' : run.usage.input_tokens.toLocaleString()}</dd></div><div><dt>Output tokens</dt><dd>{run.usage.reported?.output_tokens === false ? 'Not reported' : run.usage.output_tokens.toLocaleString()}</dd></div></dl> : <p className="empty">No run selected.</p>}<p className="meta">Reported admission usage. Excludes source extraction, transcription and exploratory experiments. No estimated price or safety score.</p></section>
      <section className="panel decision-map" aria-labelledby="decision-map-h"><div className="dashboard-heading"><h3 id="decision-map-h">Every decision</h3><span className="meta">Select a cell for evidence</span></div>
        <div className="map-legend"><span>✓ Passed checks</span><span>× Failed check</span><span>! Invalid response</span><span>· Pending</span></div>
        {!run ? <p className="empty">Run a test or select saved evidence.</p> : rows.length === 0 ? <p className="empty">No recorded requests match this filter.</p> : <><p className="matrix-scroll-hint">Scroll sideways to compare all four decisions.</p><div className="matrix-scroll" role="region" aria-label="Decision matrix" tabIndex={0}><table className="decision-matrix"><caption>Four decisions per request</caption><thead><tr><th>Request</th><th>Without · 1</th><th>Without · 2</th><th>With · 1</th><th>With · 2</th></tr></thead><tbody>{rows.map(c => <tr key={c.case_id}><th scope="row">{c.title}</th>{(['baseline', 'candidate'] as const).flatMap(side => ([1, 2] as const).map(repetition => {
          const execution = c.executions.find(e => e.side === side && e.repetition === repetition);
          const state = decisionStatus(execution);
          return <td key={`${side}:${repetition}`}><button type="button" className={`decision-cell tone-${state.tone}`} aria-label={`${c.title} - ${side === 'baseline' ? 'without' : 'with'} - repetition ${repetition}: ${state.text}`} aria-pressed={selected?.caseId === c.case_id && selected.side === side && selected.repetition === repetition} disabled={!execution} onClick={() => setSelected({ caseId: c.case_id, side, repetition })}><span aria-hidden="true">{state.symbol}</span><span>{state.text}</span></button></td>;
        }))}</tr>)}</tbody></table></div></>}
        {selectedCase && selectedExecution && run && <div className="selected-decision" aria-label="Selected decision evidence"><h3>{selectedCase.title}</h3><ExecutionDetail runId={run.id} caseId={selectedCase.case_id} exec={selectedExecution} voiceReady={health?.voice.status === 'ready' || health?.voice.status === 'degraded'} /></div>}
      </section>
      <section className="panel" aria-labelledby="saved-chart-h"><h3 id="saved-chart-h">Saved proposals</h3>{saved ? <><p className="meta">{saved.items.length} loaded{saved.truncated ? ' · partial list, not a workspace total' : ''}. Select a bar to filter the proposal selector.</p><div className="bar-chart">{CANDIDATE_STATES.map(state => <HorizontalBar key={state} label={stateLabel(state)} value={saved.items.filter(c => c.state === state).length} total={saved.items.length} pressed={candidateFilter === state} onClick={() => setCandidateFilter(old => old === state ? null : state)} />)}</div>{candidateFilter && <button type="button" className="link" onClick={() => setCandidateFilter(null)}>Show every proposal</button>}</> : <p className="empty">{savedProblem ? 'Proposal statistics unavailable.' : 'Loading saved proposals...'}</p>}</section>
      <section className="panel" aria-labelledby="availability-h"><h3 id="availability-h">Approved memory availability</h3>{memory ? <><button type="button" className="availability-chart" aria-label="Inspect approved memory availability" onClick={() => onPanel('memory')}><span className="availability-track" aria-hidden="true"><span className="availability-active" style={{ flex: activeCount }} /><span className="availability-expired" style={{ flex: expiredCount }} /></span><span>{activeCount} active · {expiredCount} expired</span></button><p className="meta">Backend snapshot at {memory.evaluated_at}{memory.truncated ? ' · partial list' : ''}. Withdrawn entries are not counted as expired.</p></> : <p className="empty">Memory availability unavailable.</p>}</section>
      <section className="panel" aria-labelledby="activity-h"><h3 id="activity-h">Review activity</h3>{history ? <><p className="meta">Loaded review events{history.truncated ? ' · partial history' : ''}; not a count of model tests.</p><div className="bar-chart">{(['approve', 'quarantine', 'revise', 'revoke'] as const).map(decision => <HorizontalBar key={decision} label={{ approve: 'Approved', quarantine: 'Rejected', revise: 'Revised', revoke: 'Withdrawn' }[decision]} value={history.events.filter(e => e.decision === decision).length} total={history.events.length} pressed={eventFilter === decision} onClick={() => setEventFilter(old => old === decision ? null : decision)} />)}</div><ul className="activity-list">{events.slice(0, 8).map(event => <li key={event.id}><strong>{event.decision}</strong> · <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>{event.reason && <p>{event.reason}</p>}</li>)}</ul>{events.length === 0 && <p className="empty">No loaded events in this selection.</p>}</> : <p className="empty">Review history unavailable.</p>}</section>
    </div>
    <section hidden={panel !== 'evidence'} aria-label="Full admission evidence">{evidence}</section>
    <section hidden={panel !== 'experiments'} aria-label="Exploratory experiments">{experiments}</section>
    <section hidden={panel !== 'memory'} aria-label="Approved memory workspace">{memoryTools}</section>
  </main>;
}
