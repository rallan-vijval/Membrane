import { useState } from 'react';
import { api, type Candidate, type CaseEvidence, type Classification, type Execution, type Run, type SelectedCase, type Side } from '../api';
import { actionLabel, attemptDiff, describeError, type ArgChange } from '../util';
import { Status } from './Chrome';

const VERDICT: Record<Classification, string> = {
  'unchanged-safe': 'No change',
  'intended-safe-change': 'Changed as intended',
  'new-policy-violation': 'Breaks policy',
  'pre-existing-violation': 'Already broken before',
  inconclusive: 'Not enough evidence',
};

const pick = (c: CaseEvidence, side: Side) => c.executions.filter((e) => e.side === side).sort((a, b) => a.repetition - b.repetition);

/** One line per side. If the two repetitions disagree, both are shown. */
function sideLabel(c: CaseEvidence, side: Side): string {
  const labels = pick(c, side).map((e) => actionLabel(e.attempt, e.error));
  if (labels.length === 0) return 'Waiting';
  return new Set(labels).size === 1 ? labels[0] : labels.map((l, i) => `Run ${i + 1}: ${l}`).join(' / ');
}

function changes(c: CaseEvidence): ArgChange[] {
  const a = pick(c, 'baseline')[0];
  const b = pick(c, 'candidate').find((e) => JSON.stringify(e.attempt) !== JSON.stringify(a?.attempt)) ?? pick(c, 'candidate')[0];
  return attemptDiff(a?.attempt ?? null, b?.attempt ?? null);
}

function ExecutionCard({ run, caseId, exec, voiceReady }: { run: Run; caseId: string; exec: Execution; voiceReady: boolean }) {
  const [clip, setClip] = useState<{ url: string; transcript: string } | null>(null);
  const [clipError, setClipError] = useState<string | null>(null);
  const listen = async () => {
    setClipError(null);
    try {
      const audio = await api.audio(run.run_id, caseId, exec.side, exec.repetition);
      setClip({ url: api.asset(audio.audio_url), transcript: audio.transcript });
    } catch (err) {
      setClipError(describeError(err)); // speech is optional: it never blocks review
    }
  };
  const outcome = exec.tool_outcome;
  return (
    <article className={`exec exec-${exec.side}`}>
      <h4>{exec.side === 'baseline' ? 'Current memory' : 'With the new memory'}, run {exec.repetition}</h4>
      {exec.error ? (
        <p className="guard guard-blocked">This run failed: {exec.error}</p>
      ) : (
        <>
          <p className="said">{exec.attempt?.answer || 'No reply text.'}</p>
          {exec.attempt?.arguments ? (
            <>
              <p className="quiet">Tried to call <code>refund_order</code> with:</p>
              <pre>{JSON.stringify(exec.attempt.arguments, null, 2)}</pre>
            </>
          ) : (
            <p className="quiet">No tool call.</p>
          )}
          {outcome && (
            <p className={outcome.allowed ? 'guard guard-allowed' : 'guard guard-blocked'}>
              {outcome.allowed ? '✓ The refund tool would allow this.' : `✕ The refund tool blocked it: ${(outcome.reasons ?? []).join('; ')}`}
              {outcome.allowed === false && ' The attempt still counts.'}
            </p>
          )}
          {exec.checks.length > 0 && (
            <ul className="checks">
              {exec.checks.map((c) => (
                <li key={c.code} className={c.passed ? 'check-pass' : 'check-fail'}>
                  <span aria-hidden="true">{c.passed ? '✓' : '✕'}</span> {c.reason || c.code}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {voiceReady && exec.attempt?.answer && (
        <div className="listen">
          <button type="button" className="text-button" onClick={() => void listen()}>Listen to this reply</button>
          {clip && <audio controls src={clip.url} aria-label={`Spoken reply: ${clip.transcript}`} />}
          {clipError && <span className="quiet"> {clipError}</span>}
        </div>
      )}
    </article>
  );
}

function CaseRow({ run, c, picked, voiceReady }: { run: Run; c: CaseEvidence; picked: SelectedCase | undefined; voiceReady: boolean }) {
  const [open, setOpen] = useState(false);
  const diff = changes(c);
  const complete = c.executions.length === 4;
  const cls: Classification = complete ? c.classification : 'inconclusive';
  return (
    <li className={`case case-${cls}${open ? ' case-open' : ''}`}>
      <button type="button" className="case-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="case-title">
          <span className="chev" aria-hidden="true">{open ? '▾' : '▸'}</span>
          {picked?.description ?? c.case_id}
        </span>
        <span className="lane lane-a">{sideLabel(c, 'baseline')}</span>
        <span className="pore" aria-hidden="true" />
        <span className="lane lane-b">{sideLabel(c, 'candidate')}</span>
        <span className="case-verdict">{complete ? VERDICT[cls] : 'Running'}</span>
      </button>
      {diff.length > 0 && (
        <p className="crossing">
          {diff.map((d) => (
            <span key={d.field} className="chip"><code>{d.field}</code> {d.from} <span aria-label="became">→</span> {d.to}</span>
          ))}
        </p>
      )}
      {open && (
        <div className="case-detail">
          {picked && (
            <p className="quiet">
              Picked because: {picked.reasons.join(', ') || 'selected'}
              {picked.semantic_score !== null && `, similarity ${picked.semantic_score.toFixed(3)}`}
            </p>
          )}
          <div className="exec-grid">
            {[...pick(c, 'baseline'), ...pick(c, 'candidate')].map((e) => (
              <ExecutionCard key={`${e.side}-${e.repetition}`} run={run} caseId={c.case_id} exec={e} voiceReady={voiceReady} />
            ))}
          </div>
        </div>
      )}
    </li>
  );
}

interface Props {
  candidate: Candidate | null;
  run: Run | null;
  voiceReady: boolean;
  locked: boolean;
  onRun: () => void;
}

export function EvidencePanel({ candidate, run, voiceReady, locked, onRun }: Props) {
  const running = run !== null && (run.status === 'queued' || run.status === 'running');
  const canRun = candidate !== null && !running && candidate.status !== 'approved';
  const done = run?.progress.completed ?? 0;
  const total = run?.progress.total ?? 48;
  const picked = new Map(run?.selection.map((s) => [s.case_id, s]) ?? []);
  const order: Classification[] = ['new-policy-violation', 'pre-existing-violation', 'inconclusive', 'intended-safe-change', 'unchanged-safe'];
  const cases = run ? [...run.cases].sort((x, y) => order.indexOf(x.classification) - order.indexOf(y.classification)) : [];
  const searched = run?.selection.filter((s) => s.semantic_score !== null).length ?? 0;

  return (
    <section className="panel panel-evidence" aria-labelledby="evidence-h">
      <h2 id="evidence-h"><span className="step">2</span> What it would change</h2>
      <p className="lede">
        The same support requests are replayed twice in fresh sessions: once with the memory the agent has now, once with the new memory added.
        What matters is what the agent tried to do, not what it said.
      </p>
      <div className="button-row">
        <button type="button" disabled={locked || !canRun} onClick={onRun}>{run ? 'Run the preview again' : 'Run the preview'}</button>
        {run && <Status value={run.status} />}
        {run && <span className="quiet">{done} of {total} replays done</span>}
      </div>

      {!candidate && <p className="empty">Stage a memory to see what it would change.</p>}
      {candidate && !run && <p className="empty">No preview yet for this candidate. Each one needs its own.</p>}

      {run && (
        <>
          <div className="progress" role="progressbar" aria-label="Replays completed" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
            <div style={{ width: `${total ? (100 * done) / total : 0}%` }} />
          </div>
          {run.selection.length > 0 && (
            <p className="quiet">
              {run.selection.length} requests chosen{searched > 0 ? `: ${searched} by Atlas Vector Search for being close to this memory, the rest fixed policy checks and their neighbors` : ''}. Open a row to see why it was picked.
            </p>
          )}
          <div className="lanes-key" aria-hidden="true">
            <span />
            <span>Current memory</span>
            <span />
            <span>With the new memory</span>
            <span>Result</span>
          </div>
          <ul className="cases">
            {cases.map((c) => <CaseRow key={c.case_id} run={run} c={c} picked={picked.get(c.case_id)} voiceReady={voiceReady} />)}
          </ul>
          {cases.length === 0 && <p className="empty">Waiting for the first replays to finish…</p>}
        </>
      )}
    </section>
  );
}
