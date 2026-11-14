import { useEffect, useRef, useState } from 'react';
import { api, type Source } from '../../api';
import { sourceFromWire } from '../../api/normalize';
import { describeError } from '../../util';
import { labPost, labRequest, rememberLabId, type DTO } from './api';

type AudioSource = DTO['AudioSource'];
const audioErrors: Record<string, string> = {
  transcription_budget: 'The workspace transcription budget is exhausted.',
  transcription_timeout: 'The provider timed out; billing may have occurred. Reload before explicitly retrying.',
  transcription_authentication: 'The ElevenLabs key was rejected.',
  transcription_permission: 'This key does not have speech-to-text access.',
  transcription_credits: 'The ElevenLabs account needs credits.',
  transcription_rate_limit: 'The provider rate limit was reached. Wait before explicitly retrying.',
  transcription_provider_rejected: 'The provider rejected this transcription request.',
  transcription_invalid_response: 'The provider returned an invalid transcript or timestamps.',
  no_speech: 'No usable speech was found. Record a clearer voice note.',
  interrupted_transcription: 'The request was interrupted. No automatic paid retry was made.',
  transcription_failed: 'Transcription failed. Reload the saved request before explicitly retrying.',
};

export function VoiceSourceIntake({ onSourceReady, disabled = false }: { onSourceReady: (source: Source) => void; disabled?: boolean }) {
  const [expanded, setExpanded] = useState(() => new URLSearchParams(window.location.search).has('audio_source'));
  const [clip, setClip] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [reviewFailed, setReviewFailed] = useState(false);
  const [audio, setAudio] = useState<AudioSource | null>(null);
  const [text, setText] = useState('');
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const playback = useRef<HTMLAudioElement | null>(null);
  const timer = useRef<number>();
  const alive = useRef(true);
  const cancelled = useRef(false);
  const chunks = useRef<Blob[]>([]);
  const submitKey = useRef(crypto.randomUUID());
  const reviewKey = useRef({ text: '', audioId: '', key: crypto.randomUUID() });
  const synthetic = api.mode === 'synthetic';
  const locked = disabled || busy || synthetic;

  useEffect(() => {
    alive.current = true;
    const stored = new URLSearchParams(window.location.search).get('audio_source');
    if (stored && !synthetic) labRequest<AudioSource>(`/audio-sources/${encodeURIComponent(stored)}`).then(a => {
      if (alive.current) { setAudio(a); setText(a.transcript ?? ''); }
    }).catch(err => { if (alive.current) setProblem(describeError(err)); });
    return () => {
      alive.current = false; cancelled.current = true; window.clearInterval(timer.current);
      if (recorder.current?.state === 'recording') recorder.current.stop();
      stream.current?.getTracks().forEach(track => track.stop());
    };
  }, [synthetic]);

  useEffect(() => {
    if (!clip) { setLocalUrl(null); return; }
    const url = URL.createObjectURL(clip); setLocalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [clip]);

  useEffect(() => {
    if (audio?.status !== 'processing') return;
    const handle = window.setTimeout(() => {
      labRequest<AudioSource>(`/audio-sources/${encodeURIComponent(audio.audio_source_id)}`).then(a => {
        setAudio(a); if (a.status === 'transcribed') setText(a.transcript ?? '');
      }).catch(err => setProblem(describeError(err)));
    }, 2000);
    return () => window.clearTimeout(handle);
  }, [audio]);

  const select = (file: File | null) => {
    if (file && file.size > 10 * 1024 * 1024) { setProblem('Choose a clip no larger than 10 MiB.'); return; }
    setClip(file); setAudio(null); setText(''); setProblem(null); submitKey.current = crypto.randomUUID();
  };
  const stop = (discard = false) => {
    cancelled.current = discard;
    window.clearInterval(timer.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
    stream.current?.getTracks().forEach(track => track.stop());
    setRecording(false);
  };
  useEffect(() => {
    if (disabled && recorder.current?.state === 'recording') stop(true);
  }, [disabled]);
  const record = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setProblem('Recording is unavailable in this browser. Upload an audio file instead.'); return; }
    setProblem(null); setBusy(true);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media; cancelled.current = false; chunks.current = [];
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const device = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
      recorder.current = device;
      let bytes = 0;
      device.ondataavailable = event => {
        bytes += event.data.size; chunks.current.push(event.data);
        if (bytes > 10 * 1024 * 1024) { stop(true); if (alive.current) setProblem('Recording exceeded 10 MiB and was discarded.'); }
      };
      device.onstop = () => {
        media.getTracks().forEach(track => track.stop()); window.clearInterval(timer.current);
        if (alive.current) {
          setRecording(false);
          if (!cancelled.current) select(new File(chunks.current, 'voice-note', { type: device.mimeType || 'audio/webm' }));
        }
      };
      device.onerror = () => { stop(true); if (alive.current) setProblem('Recording failed. Upload a saved audio clip instead.'); };
      device.start(1000); setSeconds(0); setRecording(true);
      let elapsed = 0;
      timer.current = window.setInterval(() => { elapsed++; setSeconds(elapsed); if (elapsed >= 120) stop(); }, 1000);
    } catch { stream.current?.getTracks().forEach(track => track.stop()); setProblem('Microphone access was denied or unavailable. You can upload a saved clip instead.'); }
    finally { if (alive.current) setBusy(false); }
  };
  const transcribe = async (fresh = false) => {
    if (!clip) return;
    if (fresh) submitKey.current = crypto.randomUUID();
    setBusy(true); setProblem(null);
    try {
      const data = new FormData(); data.append('file', clip);
      const result = await labRequest<AudioSource>('/audio-sources', { method: 'POST', headers: { 'Idempotency-Key': submitKey.current }, body: data });
      setAudio(result); setText(result.transcript ?? ''); rememberLabId('audio_source', result.audio_source_id);
    } catch (err) { setProblem(describeError(err)); }
    finally { setBusy(false); }
  };
  const review = async (fresh = false) => {
    if (!audio || !text.trim()) return;
    if (fresh) reviewKey.current.key = crypto.randomUUID();
    setReviewFailed(false);
    if (reviewKey.current.text !== text || reviewKey.current.audioId !== audio.audio_source_id) reviewKey.current = { text, audioId: audio.audio_source_id, key: crypto.randomUUID() };
    setBusy(true); setProblem(null);
    try {
      const source = await labRequest<DTO['Source']>(`/audio-sources/${encodeURIComponent(audio.audio_source_id)}/review`, labPost({ reviewed_text: text }, reviewKey.current.key));
      onSourceReady(sourceFromWire(source));
    } catch (err) { setReviewFailed(true); setProblem(describeError(err)); }
    finally { setBusy(false); }
  };
  return <div className="voice-source-intake">
    <div className="actions"><button type="button" className="secondary" aria-expanded={expanded} aria-controls="voice-source-controls" onClick={() => setExpanded(value => !value)}>Use a voice note instead</button></div>
    <div id="voice-source-controls" hidden={!expanded}>
    <p className="hint">Record or upload synthetic audio, up to 120 seconds and 10 MiB. ElevenLabs transcribes it; you review the text before DeepSeek proposes a memory. Speech never grants authority.</p>
    {synthetic && <p className="meta">Voice intake is disabled in synthetic mode. No audio is sent.</p>}
    <label className="field"><span>Audio source file</span><input type="file" accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/ogg,audio/webm,.mp3,.wav,.m4a,.ogg,.webm" disabled={locked || recording} onChange={e => select(e.target.files?.[0] ?? null)} /></label>
    <div className="actions">{recording ? <><span role="status">Recording: {seconds} / 120 seconds</span><button type="button" onClick={() => stop()}>Stop recording</button><button type="button" className="secondary" onClick={() => stop(true)}>Cancel recording</button></> : <button type="button" disabled={locked} onClick={() => void record()}>Record a voice note</button>}</div>
    {localUrl && <audio controls src={localUrl} aria-label="Selected audio playback" />}
    <div className="actions"><button type="button" disabled={locked || recording || !clip || audio?.status === 'processing'} onClick={() => void transcribe()}>Transcribe audio</button></div>
    {busy && <p role="status">Working on the voice source…</p>}
    {problem && <p role="status" className="panel-problem">{problem}</p>}
    {audio && <div>
      <p>Transcription: {audio.status} · {audio.duration_seconds.toFixed(1)} seconds · {audio.model}</p>
      <audio controls ref={playback} src={audio.audio_url} aria-label="Original voice source" />
      {audio.error && <p className="panel-problem">{audioErrors[audio.error] ?? audio.error} No memory was created.</p>}
      {audio.status === 'failed' && clip && <button type="button" disabled={locked} onClick={() => void transcribe(true)}>Start a new paid transcription attempt</button>}
      {audio.status === 'transcribed' && <>
        <details><summary>Original transcript and word timestamps</summary><p>{audio.transcript}</p><div className="actions">{(audio.words ?? []).map((word, i) => <button type="button" className="secondary" key={i} onClick={() => { if (playback.current) playback.current.currentTime = word.start; }}>{word.text} ({word.start.toFixed(1)}s)</button>)}</div></details>
        <label className="field"><span>Reviewed transcript</span><textarea value={text} maxLength={16000} disabled={locked} onChange={e => setText(e.target.value)} /></label>
        <p className="meta">Check order and customer identifiers carefully. Timestamps refer to the original transcript, not your corrections.</p>
        <button type="button" disabled={locked || !text.trim()} onClick={() => void review(reviewFailed)}>{reviewFailed ? "Retry proposal extraction (new paid request)" : "Confirm transcript and propose a memory"}</button>
      </>}
    </div>}
    </div>
  </div>;
}
