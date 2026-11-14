import { useEffect, useRef, useState } from 'react';
import { api, type Candidate } from '../../api';
import { describeError } from '../../util';
import { labPost, labRequest, rememberLabId, type DTO } from './api';

type Experiment = DTO['ScopeExperiment'];
export function ScopeExperimentPanel({ candidate, baseVersionId, disabled = false }: { candidate: Candidate | null; baseVersionId: string | null; disabled?: boolean }) {
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const requestKey = useRef({ identity: '', key: crypto.randomUUID() });
  const running = experiment?.status === 'queued' || experiment?.status === 'running';
  useEffect(() => {
    let alive = true;
    setExperiment(null); setProblem(null);
    const id = new URLSearchParams(window.location.search).get('experiment');
    if (id && candidate && api.mode !== 'synthetic') labRequest<Experiment>(`/experiments/${encodeURIComponent(id)}`).then(x => {
      if (alive && x.candidate_id === candidate.id) setExperiment(x);
    }).catch(err => { if (alive) setProblem(describeError(err)); });
    return () => { alive = false; };
  }, [candidate?.id]);
  useEffect(() => {
    if (!experiment || !running) return;
    let alive = true;
    const handle = window.setTimeout(() => {
      labRequest<Experiment>(`/experiments/${encodeURIComponent(experiment.experiment_id)}`).then(x => { if (alive) setExperiment(x); })
        .catch(err => { if (alive) setProblem(describeError(err)); });
    }, 2000);
    return () => { alive = false; window.clearTimeout(handle); };
  }, [experiment, running]);
  const start = async () => {
    if (!candidate || !baseVersionId) return;
    const identity = `${candidate.id}:${baseVersionId}`;
    if (requestKey.current.identity !== identity || experiment) requestKey.current = { identity, key: crypto.randomUUID() };
    setBusy(true); setProblem(null);
    try {
      const accepted = await labRequest<DTO['ExperimentAccepted']>(`/candidates/${encodeURIComponent(candidate.id)}/experiments/scope`, labPost({ base_version_id: baseVersionId }, requestKey.current.key));
      rememberLabId('experiment', accepted.experiment_id);
      setExperiment(await labRequest<Experiment>(`/experiments/${encodeURIComponent(accepted.experiment_id)}`));
    } catch (err) { setProblem(describeError(err)); }
    finally { setBusy(false); }
  };
  return <section className="panel scope-experiment" aria-labelledby="scope-experiment-h">
    <h2 id="scope-experiment-h">Explore the boundary of this memory</h2>
    <p className="hint">Seven versions of the synthetic order-4821 request, changing one logical fact at a time. Without and with the proposed memory, twice each: 28 initial decisions, at most 56 generation attempts. This experiment cannot approve or activate a memory.</p>
    {candidate && <p className="meta">Uses saved proposal {candidate.id}. Save edits as a new version before exploring them.</p>}
    <p className="meta">The proposal is deliberately included outside its scope to stress-test generalization. Production retrieval still enforces scope. The fixed trusted exception is independent of your document or recording.</p>
    <button type="button" disabled={disabled || busy || running || !candidate || !baseVersionId || api.mode === 'synthetic'} onClick={() => void start()}>{experiment ? 'Start a new scope experiment' : 'Explore this memory\u2019s scope'}</button>
    {api.mode === 'synthetic' && <p className="meta">Live exploratory experiments are disabled in synthetic mode.</p>}
    {busy && <p role="status">Preparing frozen scenarios...</p>}
    {problem && <p className="panel-problem" role="status">{problem}</p>}
    {experiment && <>
      <p role="status">Exploratory experiment: {experiment.status} - {experiment.progress.completed} / {experiment.progress.total} decisions recorded</p>
      <p className="meta">{experiment.experiment_id} - base {experiment.base_version_id} - model calls {String(experiment.usage?.model_calls ?? 0)} / 56</p>
      {experiment.error && <p className="panel-problem">{experiment.error}</p>}
      {experiment.scenarios.map(scenario => {
        const evidence = experiment.cases?.find(c => c.case_id === scenario.scenario_id);
        return <details key={scenario.scenario_id} className="scope-scenario">
          <summary>{scenario.title} - {evidence?.executions.length === 4 ? evidence.classification : 'awaiting complete evidence'}</summary>
          <p><strong>Trusted rule:</strong> {scenario.rule}</p>
          <p><strong>Expected with the proposed memory:</strong> {scenario.expected_action}</p>
          <details><summary>Changed facts and frozen ground truth</summary><pre>{JSON.stringify({ changes: scenario.changed_fields, task: scenario.task, policy: scenario.policy_snapshot, profile: scenario.retrieval.profile_id, retrieved_memory_ids: scenario.retrieval.entries.map(e => e.memory_id) }, null, 2)}</pre></details>
          {evidence && <p>Repeated actions consistent: {evidence.repetition_consistent ? 'yes' : 'not established'}</p>}
          {evidence?.executions.map(execution => <article key={`${execution.side}:${execution.repetition}`}>
            <h3>{execution.side === 'baseline' ? 'Without the proposal' : 'With the proposal'} - repetition {execution.repetition}</h3>
            {execution.error && <p className="panel-problem">Invalid evidence: {execution.error}</p>}
            <p>{execution.attempt?.answer ?? 'No valid decision'}</p>
            <p>Attempted action: {execution.attempt?.action ?? 'unavailable'}</p>
            {execution.tool_outcome && <p>Tool guard: {execution.tool_outcome.allowed ? 'allowed' : 'blocked'} - {Array.isArray(execution.tool_outcome.reasons) ? execution.tool_outcome.reasons.join('; ') : 'No reason recorded'}</p>}
            <ul>{execution.checks.map(check => <li key={check.code}>{check.passed ? 'PASS' : 'FAIL'}: {check.reason}</li>)}</ul>
            <details><summary>Raw model evidence</summary><pre>{JSON.stringify(execution.raw_responses, null, 2)}</pre></details>
          </article>)}
        </details>;
      })}
    </>}
  </section>;
}
