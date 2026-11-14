import { useEffect, useRef, useState, type DragEvent } from 'react';
import {
  api,
  type ActiveMemory,
  type Candidate,
  type CaseResult,
  type CaseRetrieval,
  type Classification,
  type Execution,
  type Health,
  type History,
  type IntegrationHealth,
  type Run,
  type Scope,
  type Side,
  type Source,
  TTL_DEFAULT_SECONDS,
  TTL_MAX_SECONDS,
  TTL_MIN_SECONDS,
} from './api';
import { RetrievalEvidence } from './governed';
import { captureFrame, prepare } from './intake';
import { ExperimentSummary } from './workflow';
import { attemptDiff, describeError } from './util';

// ----------------------------------------------------------------------------- small pieces

const STATUS_ICON: Record<string, string> = {
  ready: '●', unavailable: '✕', degraded: '▲', disabled: '○',
  active: '●', expired: '▲', revoked: '✕',
  eligible: '✓', approved: '✓', quarantined: '✕', quarantine: '✕', inconclusive: '?',
  staged: '○', testing: '…', queued: '…', running: '…', completed: '✓', failed: '✕',
};

/** Status is always shown as icon + word, never color alone. */
export function Pill({ value }: { value: string }) {
  return (
    <span className={`pill pill-${value}`}>
      <span aria-hidden="true">{STATUS_ICON[value] ?? '•'}</span> {value}
    </span>
  );
}

export function scopeLabel(scope: Scope): string {
  if (scope.kind === 'global') return 'Global: every order';
  if (scope.kind === 'preference') return 'Preference';
  return `Order ${scope.order_id}${scope.customer_id ? `, customer ${scope.customer_id}` : ''} only`;
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString() : '');

// ----------------------------------------------------------------------------- header

function HealthItem({ name, item }: { name: string; item: IntegrationHealth | undefined }) {
  const status = item?.status ?? 'unavailable';
  return (
    <li title={item?.detail ?? ''}>
      <span className="health-name">{name}</span> <Pill value={status} />
    </li>
  );
}

export function Header({ health, active }: { health: Health | null; active: ActiveMemory | null }) {
  return (
    <header className="header">
      <div>
        <h1>Membrane</h1>
        <p>See what a new memory will make your agent do, before it does it.</p>
      </div>
      <div className="header-right">
        <div className="active-version">
          Active memory: <strong>{active ? `${active.version_id} (${active.entries.length} ${active.entries.length === 1 ? 'entry' : 'entries'})` : 'unknown'}</strong>
        </div>
        <ul className="health" aria-label="Integration health">
          <HealthItem name="Atlas" item={health?.database} />
          <HealthItem name="Model" item={health?.model} />
          <HealthItem name="Search" item={health?.search} />
          <HealthItem name="Voice" item={health?.voice} />
          {health?.embeddings && <HealthItem name="Embeddings" item={health.embeddings} />}
          {health?.memory_search && <HealthItem name="Memory search" item={health.memory_search} />}
          {health?.vision && <HealthItem name="Vision" item={health.vision} />}
          {health?.tracing && <HealthItem name="Tracing" item={health.tracing} />}
        </ul>
      </div>
    </header>
  );
}

// ----------------------------------------------------------------------------- left: source + candidate

interface SourcePanelProps {
  source: Source | null;
  candidate: Candidate | null;
  disabled: boolean;
  onUpload: (file: File) => void;
  onStage: (text: string, scope: Scope, ttlSeconds: number) => void;
  onRevise: (text: string, scope: Scope, ttlSeconds: number) => void;
}

export function SourcePanel({ source, candidate, disabled, onUpload, onStage, onRevise }: SourcePanelProps) {
  const [text, setText] = useState('');
  const [kind, setKind] = useState<Scope['kind']>('global');
  const [orderId, setOrderId] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [exceptionId, setExceptionId] = useState('');
  const [ttlMinutes, setTtlMinutes] = useState(String(TTL_DEFAULT_SECONDS / 60));
  const [over, setOver] = useState(false);
  const [reading, setReading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [intakeProblem, setIntakeProblem] = useState<string | null>(null);
  const [video, setVideo] = useState<{ url: string; name: string } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => () => { if (video) URL.revokeObjectURL(video.url); }, [video]);

  // Turn whatever was dropped into the one PNG/JPEG the API accepts, and say what was done.
  const take = async (file: File | undefined) => {
    if (!file || disabled) return;
    setIntakeProblem(null);
    setReading(true);
    try {
      const result = await prepare(file);
      if (result.kind === 'ready') { setNote(result.note); onUpload(result.file); }
      else if (result.kind === 'video') setVideo({ url: URL.createObjectURL(result.file), name: result.file.name });
      else setIntakeProblem(result.message);
    } finally {
      setReading(false);
    }
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    void take(e.dataTransfer.files[0]);
  };
  const useFrame = async () => {
    if (!videoRef.current || !video) return;
    try {
      const frame = await captureFrame(videoRef.current, video.name);
      setVideo(null);
      setNote(frame.note);
      onUpload(frame.file);
    } catch (err) {
      setIntakeProblem(err instanceof Error ? err.message : 'Could not capture that frame.');
    }
  };

  // Fill the editor from the current candidate, or else from the extraction's proposal.
  const seed = candidate ?? source?.proposed_candidate ?? null;
  const seedKey = candidate?.id ?? source?.id ?? '';
  useEffect(() => {
    if (!seed) return;
    setText(seed.text);
    setKind(seed.scope.kind);
    setOrderId(seed.scope.kind === 'order' ? seed.scope.order_id : '');
    setCustomerId(seed.scope.kind === 'order' ? seed.scope.customer_id ?? '' : '');
    setExceptionId(seed.scope.kind === 'order' ? seed.scope.exception_id ?? '' : '');
    // A revision starts from the lifetime of the candidate it revises.
    if (candidate) setTtlMinutes(String(Math.round(candidate.ttl_seconds / 60)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  const scope: Scope = kind === 'order' ? { kind, order_id: orderId.trim(), customer_id: customerId.trim() || null,
    exception_id: exceptionId.trim() || null } : { kind };
  const minutes = Number(ttlMinutes);
  const ttlValid = Number.isInteger(minutes) && minutes * 60 >= TTL_MIN_SECONDS && minutes * 60 <= TTL_MAX_SECONDS;
  // The backend requires an exact order AND customer for an order scope.
  const scopeValid = kind !== 'order' || (orderId.trim().length > 0 && customerId.trim().length > 0);
  const valid = text.trim().length > 0 && scopeValid && ttlValid;

  return (
    <section className="panel" aria-labelledby="source-h">
      <h2 id="source-h">1. Source and candidate</h2>

      {video ? (
        <div className="frame-picker">
          <video ref={videoRef} src={video.url} controls muted playsInline aria-label={`Preview of ${video.name}`} />
          <p className="meta">Pause on the frame that shows the note or message, then use it. Only that one frame is sent; sound is ignored.</p>
          <div className="actions">
            <button type="button" disabled={disabled} onClick={() => void useFrame()}>Use this frame</button>
            <button type="button" className="secondary" onClick={() => setVideo(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className={`dropzone${over ? ' dropzone-over' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }}
             onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <p className="dropzone-title">{reading ? 'Reading the file…' : 'Drop a file here'}</p>
          <label className="field">
            <span>Source file (image, PDF, text or video; synthetic data only)</span>
            <input
              type="file"
              accept="image/*,video/*,application/pdf,text/*,.md,.csv,.json,.log,.eml"
              disabled={disabled || reading}
              onChange={(e) => {
                void take(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
          </label>
        </div>
      )}
      {intakeProblem && <p className="intake-problem" role="status">{intakeProblem}</p>}

      {source ? (
        <div className="source">
          {source.image_url && <img src={source.image_url} alt="The source as sent to the backend" />}
          {note && <p className="conversion">{note}</p>}
          <div className="trust">
            <Pill value={source.provenance.trusted ? 'ready' : 'degraded'} />{' '}
            {source.provenance.trusted ? 'Trusted source' : 'Untrusted source: it cannot grant authority or exceptions'}
          </div>
          {source.quotation && <blockquote>{source.quotation}</blockquote>}
          <details>
            <summary>Full extracted text</summary>
            <p className="mono">{source.extracted_text}</p>
            <p className="meta">
              {source.provenance.mime_type} · sha256 {source.provenance.sha256.slice(0, 12)}… · extraction model{' '}
              {source.provenance.extraction_model ?? 'n/a'}
            </p>
          </details>
        </div>
      ) : (
        <p className="empty">Add a source to extract a proposed memory. A PDF sends page 1; a video sends the one frame you pick.</p>
      )}

      <label className="field">
        <span>Candidate memory</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} disabled={disabled || !source} />
      </label>
      <div className="row">
        <label className="field">
          <span>Scope</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as Scope['kind'])} disabled={disabled || !source}>
            <option value="global">Global</option>
            <option value="order">One order</option>
            <option value="preference">Preference</option>
          </select>
        </label>
        {kind === 'order' && (
          <>
            <label className="field">
              <span>Order ID</span>
              <input value={orderId} onChange={(e) => setOrderId(e.target.value)} disabled={disabled} />
            </label>
            <label className="field">
              <span>Customer ID</span>
              <input value={customerId} onChange={(e) => setCustomerId(e.target.value)} disabled={disabled} />
            </label>
            <label className="field">
              <span>Trusted exception reference</span>
              <input value={exceptionId} onChange={(e) => setExceptionId(e.target.value)} disabled={disabled} placeholder="e.g. exc-4821" />
            </label>
          </>
        )}
      </div>

      <label className="field">
        <span>Lifetime after approval (minutes)</span>
        <input type="number" inputMode="numeric" min={TTL_MIN_SECONDS / 60} max={TTL_MAX_SECONDS / 60} step={1} value={ttlMinutes}
               onChange={(e) => setTtlMinutes(e.target.value)} disabled={disabled || !source} aria-describedby="ttl-help" />
      </label>
      <p className="meta" id="ttl-help">
        {ttlValid ? 'The memory expires this long after it is approved, then stops being used.' : 'Enter a whole number of minutes from 1 to 1440.'}
        {kind === 'order' && !scopeValid && ' An order scope needs both the order ID and the customer ID.'}
      </p>

      <div className="actions">
        {!candidate && (
          <button type="button" disabled={disabled || !source || !valid} onClick={() => onStage(text.trim(), scope, minutes * 60)}>
            Stage candidate
          </button>
        )}
        {candidate && (
          <button type="button" className="secondary" disabled={disabled || !valid || candidate.state === 'approved' || candidate.state === 'testing'} onClick={() => onRevise(text.trim(), scope, minutes * 60)}>
            Save as revision
          </button>
        )}
      </div>

      {candidate && (
        <dl className="facts">
          <dt>Candidate</dt>
          <dd><code>{candidate.id}</code> <Pill value={candidate.state} /></dd>
          <dt>Scope</dt>
          <dd>{scopeLabel(candidate.scope)}</dd>
          <dt>Lifetime</dt>
          <dd>{Math.round(candidate.ttl_seconds / 60)} min after approval</dd>
          <dt>Lineage</dt>
          <dd>
            {candidate.parent_candidate_id ? <>revision of <code>{candidate.parent_candidate_id}</code></> : 'original'} · base{' '}
            <code>{candidate.base_version_id}</code>
          </dd>
        </dl>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------- center: run evidence

function actionLabel(exec: Execution): string {
  if (exec.error) return 'Error';
  if (exec.outcome === 'refund') {
    const waive = exec.attempt?.arguments['waive_return'];
    return waive === true ? 'Refund, return waived' : 'Refund';
  }
  return { request_return: 'Ask for return', request_verification: 'Ask for verification', answer: 'Answer, no refund', error: 'Error' }[exec.outcome];
}

const ORDER: Classification[] = ['new-policy-violation', 'pre-existing-violation', 'inconclusive', 'intended-safe-change', 'unchanged-safe'];
const firstOf = (c: CaseResult, side: Side) => c.executions.filter((e) => e.side === side).sort((a, b) => a.repetition - b.repetition);

/** The exact tool-argument differences between current memory and the candidate, for one case. */
function caseDiff(c: CaseResult) {
  const a = firstOf(c, 'baseline')[0];
  const key = (e: Execution | undefined) => JSON.stringify([e?.outcome, e?.attempt?.arguments ?? null]);
  const b = firstOf(c, 'candidate').find((e) => key(e) !== key(a)) ?? firstOf(c, 'candidate')[0];
  return a && b ? attemptDiff(a, b) : [];
}

/** One line per side; if the two repetitions disagree, show both. */
function sideSummary(c: CaseResult, side: Side): string {
  const labels = c.executions.filter((e) => e.side === side).sort((a, b) => a.repetition - b.repetition).map(actionLabel);
  if (labels.length === 0) return 'pending';
  return new Set(labels).size === 1 ? labels[0] : labels.map((l, i) => `rep ${i + 1}: ${l}`).join(' / ');
}

const CLASS_TEXT: Record<Classification, string> = {
  'unchanged-safe': 'Unchanged, safe',
  'intended-safe-change': 'Intended safe change',
  'new-policy-violation': 'New policy violation',
  'pre-existing-violation': 'Pre-existing violation',
  inconclusive: 'Inconclusive',
};

function ExecutionDetail({ runId, caseId, exec, voiceReady }: { runId: string; caseId: string; exec: Execution; voiceReady: boolean }) {
  const [audio, setAudio] = useState<{ url: string; transcript: string } | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const listen = async () => {
    setAudioError(null);
    try {
      const clip = await api.audio(runId, caseId, exec.side, exec.repetition);
      setAudio({ url: clip.audio_url, transcript: clip.transcript });
    } catch (err) {
      setAudioError(describeError(err)); // audio failure never blocks review
    }
  };
  return (
    <div className="exec">
      <h4>{exec.side === 'baseline' ? 'A · current memory' : 'B · with candidate'} · repetition {exec.repetition}</h4>
      <p className="answer">{exec.answer_text || <em>No answer text</em>}</p>
      {exec.attempt ? (
        <>
          <div className="meta">Attempted tool call: <code>{exec.attempt.tool}</code></div>
          <pre>{JSON.stringify(exec.attempt.arguments, null, 2)}</pre>
        </>
      ) : (
        <div className="meta">No tool call attempted.</div>
      )}
      {exec.enforcement && (
        <div className={exec.enforcement.allowed ? 'enforce ok' : 'enforce blocked'}>
          {exec.enforcement.allowed ? '✓ Tool guard allowed it' : '✕ Tool guard blocked it'}: {exec.enforcement.reasons.join(' ')}
        </div>
      )}
      {exec.error && <div className="enforce blocked">Error: {exec.error}</div>}
      {exec.raw_responses && exec.raw_responses.length > 0 && (
        <details><summary>Raw model response</summary><pre>{JSON.stringify(exec.raw_responses, null, 2)}</pre></details>
      )}
      {voiceReady && exec.answer_text && (
        <div className="audio">
          <button type="button" className="link" onClick={() => void listen()}>Listen to this answer</button>
          {audio && <audio controls src={audio.url} aria-label={`Spoken answer: ${audio.transcript}`} />}
          {audioError && <span className="meta"> {audioError}</span>}
        </div>
      )}
    </div>
  );
}

interface RunPanelProps {
  candidate: Candidate | null;
  run: Run | null;
  voice: IntegrationHealth | null;
  disabled: boolean;
  onRun: () => void;
}

export function RunPanel({ candidate, run, voice, disabled, onRun }: RunPanelProps) {
  const [open, setOpen] = useState<string | null>(null);
  const running = run ? run.status === 'queued' || run.status === 'running' : false;
  const canRun = candidate !== null && !running && ['staged', 'eligible', 'inconclusive'].includes(candidate.state);
  const reasons = new Map(run?.selection.map((s) => [s.fixture_id, s]) ?? []);

  return (
    <section className="panel wide" aria-labelledby="run-h">
      <h2 id="run-h">2. Behavior preview</h2>
      <p className="hint">The same frozen tasks run with current memory (A) and with the candidate added (B). Compare what the agent tried to do.</p>
      <ExperimentSummary run={run} />
      <div className="actions">
        <button type="button" disabled={disabled || !canRun} onClick={onRun}>
          {run ? 'Run test again' : 'Run behavior test'}
        </button>
        {run && <Pill value={run.status} />}
      </div>

      {!candidate && <p className="empty">Stage a candidate to test it.</p>}

      {run && (
        <>
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={run.progress.total} aria-valuenow={run.progress.completed}
               aria-label="Executions completed">
            <div style={{ width: `${run.progress.total ? (100 * run.progress.completed) / run.progress.total : 0}%` }} />
          </div>
          <p className="meta">{run.progress.completed} of {run.progress.total} executions{run.trace_url && <> · <a href={run.trace_url} target="_blank" rel="noreferrer">Open trace</a></>}</p>

          <details>
            <summary>Why these {run.selection.length} test cases were picked</summary>
            <ul className="selection">
              {run.selection.map((s) => (
                <li key={s.fixture_id}>
                  <span className={`tag tag-${s.reason}`}>{s.reason}</span> {s.title}
                  {s.reasons && <span className="meta"> · {s.reasons.join(', ')}</span>}
                  {s.score !== null && <span className="meta"> · similarity {s.score.toFixed(3)}</span>}
                </li>
              ))}
            </ul>
          </details>

          {run.errors.length > 0 && <ul className="run-errors">{run.errors.map((e) => <li key={e}>{e}</li>)}</ul>}

          <table>
            <thead>
              <tr><th scope="col">Case</th><th scope="col">A · current</th><th className="pore-head" aria-hidden="true" /><th scope="col">B · with candidate</th><th scope="col">Result</th></tr>
            </thead>
            <tbody>
              {[...run.cases].sort((x, y) => ORDER.indexOf(x.classification ?? 'inconclusive') - ORDER.indexOf(y.classification ?? 'inconclusive')).map((c) => {
                const expanded = open === c.case_id;
                const cls = c.classification ?? 'inconclusive';
                return (
                  <CaseRows key={c.case_id} c={c} cls={cls} expanded={expanded} runId={run.id}
                            retrieval={run.memory_retrieval.find((r) => r.case_id === c.case_id)} runHasProvenance={run.memory_retrieval.length > 0}
                            candidateText={candidate && candidate.id === run.candidate_id ? candidate.text : null}
                            pickedBy={reasons.get(c.fixture_id)?.reason ?? null} voiceReady={voice?.status === 'ready' || voice?.status === 'degraded'}
                            onToggle={() => setOpen(expanded ? null : c.case_id)} />
                );
              })}
            </tbody>
          </table>
          {run.cases.length === 0 && <p className="empty">Waiting for the first results…</p>}
        </>
      )}
    </section>
  );
}

function CaseRows({ c, cls, expanded, runId, pickedBy, voiceReady, onToggle, retrieval, runHasProvenance, candidateText }: {
  c: CaseResult; cls: Classification; expanded: boolean; runId: string; pickedBy: string | null; voiceReady: boolean; onToggle: () => void;
  retrieval: CaseRetrieval | undefined; runHasProvenance: boolean; candidateText: string | null;
}) {
  const diff = c.classification ? caseDiff(c) : [];
  return (
    <>
      <tr className={`case case-${cls}`}>
        <th scope="row">
          <button type="button" className="link" aria-expanded={expanded} onClick={onToggle}>
            {expanded ? '▾' : '▸'} {c.title}
          </button>
          {pickedBy && <span className="meta"> · {pickedBy}</span>}
        </th>
        <td className="a-cell">{sideSummary(c, 'baseline')}</td>
        <td className="pore" aria-hidden="true"><span /></td>
        <td className="b-cell">
          {sideSummary(c, 'candidate')}
          {diff.length > 0 && (
            <span className="crossing">
              {diff.map((d) => <span key={d.field} className="chip"><code>{d.field}</code> {d.from} → {d.to}</span>)}
            </span>
          )}
        </td>
        <td className="result">{c.classification ? CLASS_TEXT[cls] : 'Pending'}</td>
      </tr>
      {expanded && (
        <tr className="detail">
          <td colSpan={5}>
            {c.check_reasons.length > 0 && <ul className="checks">{c.check_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            <RetrievalEvidence retrieval={retrieval} runHasProvenance={runHasProvenance} candidateText={candidateText} />
            <div className="exec-grid">
              {[...c.executions]
                .sort((a, b) => a.side.localeCompare(b.side) || a.repetition - b.repetition)
                .map((e) => <ExecutionDetail key={`${e.side}-${e.repetition}`} runId={runId} caseId={c.case_id} exec={e} voiceReady={voiceReady} />)}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ----------------------------------------------------------------------------- right: decision

interface DecisionPanelProps {
  candidate: Candidate | null;
  run: Run | null;
  disabled: boolean;
  onApprove: () => void;
  onQuarantine: (reason: string) => void;
}

export function DecisionPanel({ candidate, run, disabled, onApprove, onQuarantine }: DecisionPanelProps) {
  const [reason, setReason] = useState('');
  // Approval is offered only when the BACKEND says both the candidate and this run are eligible.
  const eligible = candidate?.state === 'eligible' && run?.status === 'completed' && run.admission === 'eligible'
    && run.candidate_id === candidate.id && candidate.latest_run_id === run.id;
  const decided = candidate?.state === 'approved' || candidate?.state === 'quarantined';

  return (
    <section className="panel" aria-labelledby="decision-h">
      <h2 id="decision-h">3. Decision</h2>
      {!candidate && <p className="empty">Nothing to decide yet.</p>}
      {candidate && (
        <>
          <p>Candidate is <Pill value={candidate.state} /></p>
          {run?.admission ? (
            <div className={`verdict verdict-${run.admission}`}>
              <strong>
                {run.admission === 'eligible' && (candidate.state === 'approved' ? '✓ Approved and active' : '✓ Eligible for approval')}
                {run.admission === 'quarantine' && '✕ Should be quarantined'}
                {run.admission === 'inconclusive' && '? Inconclusive: investigate or retest'}
              </strong>
              <ul>{run.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              {run.cases.length > 0 && (
                <p className="tally">
                  Of {run.cases.length} cases: {ORDER.map((k) => [run.cases.filter((c) => (c.classification ?? 'inconclusive') === k).length, CLASS_TEXT[k].toLowerCase()] as const)
                    .filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`).join(', ')}.
                </p>
              )}
            </div>
          ) : (
            <p className="hint">Run the behavior test to get an admission result.</p>
          )}

          <div className="actions stack">
            <button type="button" disabled={disabled || !eligible} onClick={onApprove}>Approve and activate</button>
            {!eligible && candidate.state !== 'approved' && (
              <p className="meta">Approval unlocks only when the backend reports an eligible run for this exact candidate.</p>
            )}
            <label className="field">
              <span>Quarantine reason</span>
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. waives returns for every VIP" disabled={disabled || decided} />
            </label>
            <button type="button" className="danger" disabled={disabled || decided || reason.trim().length === 0}
                    onClick={() => onQuarantine(reason.trim())}>
              Quarantine
            </button>
            <p className="meta">To narrow the memory instead, edit the text and scope on the left and save it as a revision. A revision must pass its own test.</p>
          </div>
        </>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------- footer

export function Footer({ history, active, run, mode }: { history: History | null; active: ActiveMemory | null; run: Run | null; mode: 'real' | 'synthetic' }) {
  return (
    <footer className="footer">
      <details>
        <summary>History and run details</summary>
        <div className="footer-grid">
          <div>
            <h3>Memory in force</h3>
            {active && active.entries.length > 0 ? (
              <ul className="timeline">
                {active.entries.map((m) => (
                  <li key={m.id}>{m.text}<div className="meta">{scopeLabel(m.scope)}{m.candidate_id ? `, from ${m.candidate_id}` : ', seeded policy'}</div></li>
                ))}
              </ul>
            ) : <p className="empty">Nothing loaded.</p>}
          </div>
          <div>
            <h3>Run</h3>
            {run ? (
              <dl className="facts">
                <dt>Run</dt><dd><code>{run.id}</code> <span className="tag">{mode === 'synthetic' ? 'synthetic' : run.recorded ? 'recorded' : 'live'}</span></dd>
                <dt>Model</dt><dd>{run.model_config.provider} / {run.model_config.agent_model} · temperature {run.model_config.temperature ?? 'default'}</dd>
                <dt>Usage</dt><dd>{run.usage.model_calls} calls · {run.usage.input_tokens + run.usage.output_tokens} tokens · {(run.usage.latency_ms / 1000).toFixed(1)} s</dd>
                <dt>Started</dt><dd>{when(run.created_at)}{run.completed_at ? ` · finished ${when(run.completed_at)}` : ''}</dd>
              </dl>
            ) : <p className="empty">No run selected.</p>}
          </div>
          <div>
            <h3>Memory versions</h3>
            {history && history.versions.length > 0 ? (
              <ol className="timeline">
                {history.versions.map((v) => (
                  <li key={v.version_id}>
                    <code>{v.version_id}</code> {when(v.activated_at)}
                    {v.candidate_id && <span className="meta"> · from {v.candidate_id}, run {v.run_id}</span>}
                  </li>
                ))}
              </ol>
            ) : <p className="empty">No versions loaded.</p>}
          </div>
          <div>
            <h3>Reviewer events</h3>
            {history && history.events.length > 0 ? (
              <ol className="timeline">
                {history.events.map((e) => (
                  <li key={e.id}>
                    <Pill value={e.decision === 'approve' ? 'approved' : e.decision === 'quarantine' ? 'quarantined' : e.decision === 'revoke' ? 'revoked' : 'staged'} /> {e.decision} of <code>{e.memory_id ?? e.candidate_id}</code> by {e.actor} (demo identity) {when(e.created_at)}
                    {e.reason && <div className="meta">{e.reason}</div>}
                  </li>
                ))}
              </ol>
            ) : <p className="empty">No reviewer events yet.</p>}
            {history?.truncated && <p className="meta">Showing the latest 100 only.</p>}
          </div>
        </div>
      </details>
    </footer>
  );
}
