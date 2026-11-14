/**
 * Governed-memory phase UI (docs/NEXT_PHASE_PLAN.md, Task B):
 * the memory panel with expiry and revoke, per-case retrieval evidence,
 * and the bounded "run with active memory" panel.
 */
import { useEffect, useRef, useState } from 'react';
import { api, type ActiveExecution, type CaseRetrieval, type GovernedMemory, type RetrievedMemory, type TaskOption } from './api';
import { Pill, scopeLabel } from './components';
import { describeError } from './util';

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

/** "in 4 min", "in 38 s". Informational only: the backend's `availability` is the authority. */
function untilLabel(expiresAt: string, from: number): string {
  const seconds = Math.round((Date.parse(expiresAt) - from) / 1000);
  if (seconds <= 0) return 'now';
  if (seconds > 365 * 86400) return 'no planned expiry';
  if (seconds >= 7200) return `in ${Math.round(seconds / 3600)} h`;
  if (seconds >= 120) return `in ${Math.round(seconds / 60)} min`;
  return `in ${seconds} s`;
}

// ----------------------------------------------------------------------------- memory in force

interface MemoryPanelProps {
  memory: GovernedMemory | null;
  problem: string | null;
  disabled: boolean;
  onRevoke: (memoryId: string, reason: string) => void;
  /** Ask the backend again, e.g. when an expiry time has passed. */
  onRefresh: () => void;
}

export function MemoryPanel({ memory, problem, disabled, onRevoke, onRefresh }: MemoryPanelProps) {
  const [revoking, setRevoking] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [tick, setTick] = useState(() => Date.now());
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  // When the next expiry passes, ask the backend what is in force. The browser clock only
  // schedules the question; it never decides the answer.
  const nextExpiry = memory?.items.filter((m) => m.availability === 'active').map((m) => Date.parse(m.expires_at)).filter((t) => t > Date.now()).sort((a, b) => a - b)[0];
  useEffect(() => {
    if (!nextExpiry) return;
    const delay = nextExpiry - Date.now() + 1000;
    if (delay > 24 * 3600 * 1000) return;
    const timer = window.setTimeout(() => refresh.current(), delay);
    return () => window.clearTimeout(timer);
  }, [nextExpiry]);

  useEffect(() => {
    const timer = window.setInterval(() => setTick(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="panel" aria-labelledby="memory-h">
      <h2 id="memory-h">Approved memories</h2>
      <p className="hint">What the live agent can be given right now. Each memory has an owner version, a scope and an expiry. Expired memories stay on record but are no longer used.</p>
      {problem && <p className="panel-problem" role="status">{problem}</p>}
      {!memory && !problem && <p className="empty">Loading…</p>}
      {memory && (
        <>
          <p className="meta">Version <code>{memory.version_id}</code>, evaluated by the backend at {clock(memory.evaluated_at)}.{memory.truncated ? ' Showing the first 100.' : ''}</p>
          {memory.items.length === 0 && <p className="empty">No memories in this version.</p>}
          <ul className="memory-list">
            {memory.items.map((m) => (
              <li key={m.id} className={`memory memory-${m.availability}`}>
                <div className="memory-main">
                  <p className="memory-text">{m.text}</p>
                  <p className="meta">
                    <Pill value={m.availability} /> {m.availability === 'active' ? '' : 'No longer used · '}{scopeLabel(m.scope)} ·{' '}
                    {m.availability !== 'active' ? `expired at ${clock(m.expires_at)}` : untilLabel(m.expires_at, tick) === 'no planned expiry' ? 'no planned expiry' : `expires ${untilLabel(m.expires_at, tick)} (${clock(m.expires_at)})`}
                  </p>
                  <p className="meta"><code>{m.id}</code> from {m.candidate_id ? <code>{m.candidate_id}</code> : 'seeded policy'}, activated in <code>{m.version_id}</code></p>
                </div>
                {m.availability === 'active' && revoking !== m.id && (
                  <button type="button" className="danger" disabled={disabled} onClick={() => { setRevoking(m.id); setReason(''); }}>Revoke</button>
                )}
                {revoking === m.id && (
                  <div className="revoke-form">
                    <label className="field">
                      <span>Reason for revoking {m.id}</span>
                      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. exception withdrawn by supervisor" disabled={disabled} />
                    </label>
                    <div className="actions">
                      <button type="button" className="danger" disabled={disabled || reason.trim().length === 0}
                              onClick={() => { onRevoke(m.id, reason.trim()); setRevoking(null); }}>
                        Confirm revoke
                      </button>
                      <button type="button" className="secondary" onClick={() => setRevoking(null)}>Cancel</button>
                    </div>
                    <p className="meta">Revoking creates a new memory version without this entry. The old version and its evidence stay on record.</p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------- retrieval evidence

function RetrievedList({ entries }: { entries: RetrievedMemory[] }) {
  if (entries.length === 0) return <p className="meta">No active memory matched this case.</p>;
  return (
    <ul className="retrieved">
      {entries.map((m) => (
        <li key={m.id}>
          {m.text}
          <div className="meta">
            <span className={`tag ${m.reason === 'exact_scope' ? 'tag-sentinel' : 'tag-vector'}`}>{m.reason === 'exact_scope' ? 'exact scope' : 'semantic'}</span>{' '}
            {m.score !== null ? `similarity ${m.score.toFixed(3)} · ` : ''}{scopeLabel(m.scope)} · expires {clock(m.expires_at)} · <code>{m.id}</code>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Which memories the agent was given for a case. Separate from why the test case was picked. */
export function RetrievalEvidence({ retrieval, runHasProvenance, candidateText }: { retrieval: CaseRetrieval | undefined; runHasProvenance: boolean; candidateText?: string | null }) {
  return (
    <div className="retrieval">
      <h4>Memory the agent was given</h4>
      {!runHasProvenance ? (
        <p className="meta">Retrieval provenance unavailable for this run. It was recorded before memory retrieval was tracked.</p>
      ) : !retrieval ? (
        <p className="meta">No retrieval record for this case.</p>
      ) : (
        <>
          <p className="meta">Frozen at {clock(retrieval.retrieval_at)} from <code>{retrieval.base_version_id}</code> and reused for both sides and both repetitions.</p>
          <RetrievedList entries={retrieval.entries} />
          {candidateText && <p className="overlay"><span className="tag">B only</span> plus the candidate under test: “{candidateText}”</p>}
        </>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------- run with active memory

function attemptLine(x: ActiveExecution): string {
  const e = x.execution;
  if (e.error) return `Run failed: ${e.error}`;
  if (e.outcome === 'refund') return e.attempt?.arguments['waive_return'] === true ? 'Refund, return waived' : 'Refund';
  return { request_return: 'Ask for return', request_verification: 'Ask for verification', answer: 'Answer, no refund', error: 'Run failed' }[e.outcome];
}

interface ActiveTaskPanelProps {
  /** The version the live agent runs on. Sent explicitly so a stale page cannot run against old memory. */
  versionId: string | null;
  disabled: boolean;
  /** Changes whenever active memory may have changed, to reload the task list lazily. */
  onStale: () => void;
}

export function ActiveTaskPanel({ versionId, disabled, onStale }: ActiveTaskPanelProps) {
  const [tasks, setTasks] = useState<TaskOption[] | null>(null);
  const [fixtureId, setFixtureId] = useState('');
  const [runs, setRuns] = useState<ActiveExecution[]>([]);
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.listTasks().then((items) => {
      if (!alive) return;
      setTasks(items);
      setFixtureId((current) => current || items[0]?.fixture_id || '');
    }).catch((err) => {
      if (alive) { setTasks([]); setProblem(`Tasks could not be loaded: ${describeError(err)}`); }
    });
    // Reload a stored execution named in the URL without calling the model again.
    const stored = new URLSearchParams(window.location.search).get('execution');
    if (stored) api.getExecution(stored).then((x) => { if (alive) { setRuns([x]); setFixtureId(x.fixture_id); } }).catch(() => undefined);
    return () => { alive = false; };
  }, []);

  const run = async () => {
    if (!versionId || !fixtureId) return;
    setProblem(null);
    setWorking(true);
    try {
      const x = await api.executeTask(fixtureId, versionId);
      setRuns((prev) => [x, ...prev]);
      const p = new URLSearchParams(window.location.search);
      p.set('execution', x.id);
      window.history.replaceState(null, '', `?${p.toString()}`);
    } catch (err) {
      setProblem(describeError(err));
      onStale();
    } finally {
      setWorking(false);
    }
  };

  const title = (id: string) => tasks?.find((t) => t.fixture_id === id)?.description ?? id;
  return (
    <section className="panel" aria-labelledby="active-task-h">
      <h2 id="active-task-h">Try the current AI</h2>
      <p className="hint">Ask the live agent to handle one synthetic request using only the memory in force. Run it before and after an approval, a revoke or an expiry to see the behavior change. This is not admission evidence and cannot unlock approval.</p>
      <div className="row">
        <label className="field task-field">
          <span>Request</span>
          <select value={fixtureId} disabled={disabled || working || !tasks?.length} onChange={(e) => setFixtureId(e.target.value)}>
            {(tasks ?? []).map((t) => <option key={t.fixture_id} value={t.fixture_id}>{t.description}</option>)}
          </select>
        </label>
      </div>
      <div className="actions">
        <button type="button" disabled={disabled || working || !versionId || !fixtureId} onClick={() => void run()}>
          {working ? 'Running…' : 'Try the current AI'}
        </button>
        <span className="meta">{versionId ? <>Against <code>{versionId}</code>. The refund tool is simulated.</> : 'Active memory is not loaded.'}</span>
      </div>
      {problem && <p className="panel-problem" role="status">{problem}</p>}
      {runs.length === 0 && !problem && <p className="empty">No runs yet.</p>}
      <ol className="active-runs">
        {runs.map((x, index) => (
          <li key={x.id} className={index === 0 ? 'active-run active-run-latest' : 'active-run'}>
            <p className="active-run-head">
              <strong>{attemptLine(x)}</strong> <span className="meta">· {title(x.fixture_id)} · <code>{x.version_id}</code> · {clock(x.created_at)}</span>
            </p>
            <p className="answer">{x.execution.answer_text || <em>No answer text</em>}</p>
            {x.execution.attempt && <pre>{JSON.stringify(x.execution.attempt.arguments, null, 2)}</pre>}
            {x.execution.enforcement && (
              <div className={x.execution.enforcement.allowed ? 'enforce ok' : 'enforce blocked'}>
                {x.execution.enforcement.allowed ? '✓ Tool guard allowed it' : '✕ Tool guard blocked it'}{x.execution.enforcement.reasons.length ? `: ${x.execution.enforcement.reasons.join(' ')}` : ''}
              </div>
            )}
            {x.execution.checks && x.execution.checks.length > 0 && (
              <ul className="checks">{x.execution.checks.map((c) => <li key={c.code}>{c.passed ? '✓' : '✕'} {c.code}: {c.reason}</li>)}</ul>
            )}
            <details>
              <summary>Memory the agent was given ({x.retrieval.entries.length})</summary>
              <RetrievedList entries={x.retrieval.entries} />
            </details>
            {x.execution.raw_responses && x.execution.raw_responses.length > 0 && (
              <details><summary>Raw model response</summary><pre>{JSON.stringify(x.execution.raw_responses, null, 2)}</pre></details>
            )}
            <p className="meta"><code>{x.id}</code>{x.model ? ` · model ${x.model}` : ''}{x.trace_url && <> · <a href={x.trace_url} target="_blank" rel="noreferrer">Open trace</a></>}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
