import { useEffect, useRef, useState, type DragEvent } from 'react';
import { api, type Candidate, type Scope, type ScopeKind, type Source } from '../api';
import { captureFrame, prepare } from '../intake';
import { scopeLabel } from '../util';
import { Status } from './Chrome';

interface Props {
  source: Source | null;
  intakeNote: string | null;
  candidate: Candidate | null;
  recent: Candidate[];
  locked: boolean;
  onUpload: (file: File, note: string | null) => void;
  onStage: (text: string, scope: Scope) => void;
  onRevise: (text: string, scope: Scope) => void;
  onOpenRecent: (candidateId: string) => void;
  onError: (message: string | null) => void;
}

export function IntakePanel({ source, intakeNote, candidate, recent, locked, onUpload, onStage, onRevise, onOpenRecent, onError }: Props) {
  const [over, setOver] = useState(false);
  const [reading, setReading] = useState(false);
  const [video, setVideo] = useState<{ url: string; name: string } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const pickRef = useRef<HTMLInputElement>(null);

  const [text, setText] = useState('');
  const [kind, setKind] = useState<ScopeKind>('global');
  const [orderId, setOrderId] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [exceptionId, setExceptionId] = useState('');

  // Fill the editor from the open candidate, or else from what the extraction proposed.
  const seedKey = candidate?.candidate_id ?? source?.source_id ?? '';
  useEffect(() => {
    const seedText = candidate?.text ?? source?.proposed_text;
    const seedScope = candidate?.scope ?? source?.proposed_scope;
    if (seedText === undefined) return;
    setText(seedText);
    setKind(seedScope?.kind ?? 'global');
    setOrderId(seedScope?.order_id ?? '');
    setCustomerId(seedScope?.customer_id ?? '');
    setExceptionId(seedScope?.exception_id ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  useEffect(() => () => { if (video) URL.revokeObjectURL(video.url); }, [video]);

  const take = async (file: File | undefined) => {
    if (!file || locked) return;
    onError(null);
    setReading(true);
    try {
      const result = await prepare(file);
      if (result.kind === 'ready') onUpload(result.file, result.note);
      else if (result.kind === 'video') setVideo({ url: URL.createObjectURL(result.file), name: result.file.name });
      else onError(result.message);
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
      const { file, note } = await captureFrame(videoRef.current, video.name);
      setVideo(null);
      onUpload(file, note);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Could not capture that frame.');
    }
  };

  const scope: Scope =
    kind === 'global'
      ? { kind, order_id: null, customer_id: null, exception_id: null }
      : { kind, order_id: kind === 'order' ? orderId.trim() || null : null, customer_id: customerId.trim() || null, exception_id: kind === 'order' ? exceptionId.trim() || null : null };
  const valid = text.trim().length > 0 && (kind !== 'order' || orderId.trim().length > 0) && (kind !== 'preference' || customerId.trim().length > 0);
  const unchanged = candidate !== null && candidate.text === text.trim() && JSON.stringify({ k: candidate.scope.kind ?? 'global', o: candidate.scope.order_id ?? null, c: candidate.scope.customer_id ?? null, e: candidate.scope.exception_id ?? null }) === JSON.stringify({ k: scope.kind, o: scope.order_id, c: scope.customer_id, e: scope.exception_id });

  return (
    <section className="panel" aria-labelledby="intake-h">
      <h2 id="intake-h"><span className="step">1</span> What the agent saw</h2>

      {video ? (
        <div className="frame-picker">
          <video ref={videoRef} src={video.url} controls muted playsInline aria-label={`Preview of ${video.name}`} />
          <p className="quiet">Pause on the frame that shows the note or message, then use it. Only that one frame is sent.</p>
          <div className="button-row">
            <button type="button" onClick={() => void useFrame()} disabled={locked}>Use this frame</button>
            <button type="button" className="quiet-button" onClick={() => setVideo(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div
          className={`dropzone${over ? ' dropzone-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <p className="dropzone-title">{reading ? 'Reading the file…' : 'Drop a file here'}</p>
          <p className="quiet">Screenshot or photo, PDF, text note, or a screen recording. Synthetic data only.</p>
          <button type="button" className="quiet-button" disabled={locked || reading} onClick={() => pickRef.current?.click()}>Choose a file</button>
          <input
            ref={pickRef}
            type="file"
            className="visually-hidden"
            tabIndex={-1}
            aria-label="Choose a source file"
            accept="image/*,video/*,application/pdf,text/*,.md,.csv,.json,.log,.eml"
            onChange={(e) => { void take(e.target.files?.[0]); e.target.value = ''; }}
          />
        </div>
      )}

      {source && !video && (
        <div className="source">
          <img src={api.asset(source.image_url)} alt="The source as sent to the backend" />
          {intakeNote && <p className="conversion">{intakeNote}</p>}
          <p className="trust"><Status value="degraded" label="untrusted source" /> It can suggest a memory. It cannot grant an exception or verify anyone.</p>
          {source.quotation && <blockquote>{source.quotation}</blockquote>}
          <details>
            <summary>Everything that was read from it</summary>
            <p className="extracted">{source.extracted_text || 'No text was extracted.'}</p>
            <p className="quiet">{source.mime_type}, sha256 {source.sha256.slice(0, 12)}</p>
          </details>
        </div>
      )}

      <h3 className="subhead">What the agent wants to remember</h3>
      <label className="field">
        <span>Memory</span>
        <textarea value={text} rows={4} disabled={locked || !source} onChange={(e) => setText(e.target.value)}
                  placeholder={source ? '' : 'Add a source first. The proposed memory appears here.'} />
      </label>
      <label className="field">
        <span>Applies to</span>
        <select value={kind} disabled={locked || !source} onChange={(e) => setKind(e.target.value as ScopeKind)}>
          <option value="global">Every order</option>
          <option value="order">One order only</option>
          <option value="preference">One customer's preference</option>
        </select>
      </label>
      {kind !== 'global' && (
        <div className="field-row">
          {kind === 'order' && (
            <label className="field"><span>Order</span><input value={orderId} disabled={locked} onChange={(e) => setOrderId(e.target.value)} placeholder="4821" /></label>
          )}
          <label className="field"><span>Customer</span><input value={customerId} disabled={locked} onChange={(e) => setCustomerId(e.target.value)} placeholder="customer-4821" /></label>
          {kind === 'order' && (
            <label className="field"><span>Exception on file</span><input value={exceptionId} disabled={locked} onChange={(e) => setExceptionId(e.target.value)} placeholder="exc-4821" /></label>
          )}
        </div>
      )}

      <div className="button-row">
        {!candidate ? (
          <button type="button" disabled={locked || !source || !valid} onClick={() => onStage(text.trim(), scope)}>Stage this memory</button>
        ) : (
          <button type="button" disabled={locked || !valid || unchanged} onClick={() => onRevise(text.trim(), scope)}>Save as a revision</button>
        )}
      </div>
      {candidate ? (
        <p className="quiet">
          <Status value={candidate.status} /> <code>{candidate.candidate_id}</code>, {scopeLabel(candidate.scope).toLowerCase()}
          {candidate.parent_candidate_id ? <>. Revision of <code>{candidate.parent_candidate_id}</code>.</> : '.'}{' '}
          {unchanged ? 'Edit the memory or its scope to make a narrower revision.' : 'A revision is a new candidate and needs its own preview.'}
        </p>
      ) : (
        <p className="quiet">Staging keeps the memory apart from the live agent. Nothing changes until it passes a preview and you approve it.</p>
      )}

      {recent.length > 0 && (
        <label className="field">
          <span>Open an earlier candidate</span>
          <select value="" disabled={locked} onChange={(e) => e.target.value && onOpenRecent(e.target.value)}>
            <option value="">Choose…</option>
            {recent.slice(0, 20).map((c) => (
              <option key={c.candidate_id} value={c.candidate_id}>{c.status}: {c.text.slice(0, 60)}</option>
            ))}
          </select>
        </label>
      )}
    </section>
  );
}
