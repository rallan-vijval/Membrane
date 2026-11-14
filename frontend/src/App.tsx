import { useCallback, useEffect, useRef, useState } from 'react';
import { api, TERMINAL_RUN, type Candidate, type Health, type History, type Run, type Scope, type Source, type Version } from './api';
import { DecisionPanel } from './components/DecisionPanel';
import { EvidencePanel } from './components/EvidencePanel';
import { Footer, Header } from './components/Chrome';
import { IntakePanel } from './components/IntakePanel';
import { describeError } from './util';

const POLL_MS = 2000;

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  return { candidate: p.get('candidate'), run: p.get('run') };
}

function writeUrl(candidateId: string | null, runId: string | null) {
  const p = new URLSearchParams(window.location.search);
  if (candidateId) p.set('candidate', candidateId);
  else p.delete('candidate');
  if (runId) p.set('run', runId);
  else p.delete('run');
  const query = p.toString();
  window.history.replaceState(null, '', query ? `?${query}` : window.location.pathname);
}

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [active, setActive] = useState<Version | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [recent, setRecent] = useState<Candidate[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [intakeNote, setIntakeNote] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const alive = useRef(true);

  const fail = useCallback((err: unknown) => {
    if (alive.current) setError(describeError(err));
  }, []);

  /** The backend is the only authority on active memory: always re-read, never infer. */
  const refreshShared = useCallback(async () => {
    const [h, a, hist, list] = await Promise.allSettled([api.health(), api.activeMemory(), api.history(), api.listCandidates()]);
    if (!alive.current) return;
    if (h.status === 'fulfilled') setHealth(h.value);
    if (a.status === 'fulfilled') setActive(a.value);
    if (hist.status === 'fulfilled') setHistory(hist.value);
    if (list.status === 'fulfilled') setRecent(list.value.items);
    // Health explains missing configuration; only surface a separate error when health itself failed.
    if (h.status === 'rejected') fail(h.reason);
  }, [fail]);

  const open = useCallback(
    async (candidateId: string, runId: string | null) => {
      const c = await api.getCandidate(candidateId);
      if (!alive.current) return;
      setCandidate(c);
      setIntakeNote(null);
      api.getSource(c.source_id).then((s) => alive.current && setSource(s)).catch(fail);
      const id = runId ?? c.latest_run_id ?? null;
      const r = id ? await api.getRun(id) : null;
      if (alive.current) setRun(r);
    },
    [fail],
  );

  // First load, including a reload with ?candidate=…&run=… in the URL.
  useEffect(() => {
    alive.current = true;
    void (async () => {
      await refreshShared();
      const url = readUrl();
      if (url.candidate) await open(url.candidate, url.run).catch(fail);
    })();
    return () => {
      alive.current = false;
    };
  }, [refreshShared, open, fail]);

  useEffect(() => {
    writeUrl(candidate?.candidate_id ?? null, run?.run_id ?? null);
  }, [candidate?.candidate_id, run?.run_id]);

  // Poll a run every two seconds until it is terminal or the page goes away.
  const runId = run?.run_id ?? null;
  const runDone = run ? TERMINAL_RUN.has(run.status) : true;
  useEffect(() => {
    if (!runId || runDone) return;
    let stopped = false;
    const tick = async () => {
      try {
        const next = await api.getRun(runId);
        // On the final poll, read the candidate first: setting a terminal run ends this effect.
        const c = TERMINAL_RUN.has(next.status) ? await api.getCandidate(next.candidate_id) : null;
        if (stopped) return;
        if (c) setCandidate(c);
        setRun(next);
      } catch (err) {
        if (!stopped) fail(err);
      }
    };
    const timer = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [runId, runDone, fail]);

  const act = async (label: string, fn: () => Promise<void>) => {
    setError(null);
    setBusy(label);
    try {
      await fn();
    } catch (err) {
      fail(err);
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const onUpload = (file: File, note: string | null) =>
    act('Reading the source…', async () => {
      const s = await api.uploadSource(file);
      setSource(s);
      setIntakeNote(note);
      setCandidate(null);
      setRun(null);
    });

  const onStage = (text: string, scope: Scope) =>
    act('Staging the memory…', async () => {
      if (!source) throw new Error('Add a source first.');
      if (!active) throw new Error('Active memory is not loaded, so there is nothing to stage against. Check the backend.');
      const c = await api.createCandidate({ source_id: source.source_id, text, scope, base_version_id: active.version_id });
      setCandidate(c);
      setRun(null);
      await refreshShared();
    });

  const onRevise = (text: string, scope: Scope) =>
    act('Saving the revision…', async () => {
      if (!candidate) return;
      const child = await api.revise(candidate.candidate_id, { text, scope });
      setCandidate(child);
      setRun(null);
      await refreshShared();
    });

  const onRun = () =>
    act('Starting the preview…', async () => {
      if (!candidate) return;
      const { run_id } = await api.startRun(candidate.candidate_id);
      const [r, c] = await Promise.all([api.getRun(run_id), api.getCandidate(candidate.candidate_id)]);
      setRun(r);
      setCandidate(c);
    });

  const onApprove = (reason: string) =>
    act('Approving…', async () => {
      if (!candidate || !run) return;
      try {
        setCandidate(await api.approve(candidate.candidate_id, { run_id: run.run_id, reason }));
      } finally {
        await refreshShared();
      }
    });

  const onQuarantine = (reason: string) =>
    act('Quarantining…', async () => {
      if (!candidate) return;
      try {
        setCandidate(await api.quarantine(candidate.candidate_id, reason));
      } finally {
        await refreshShared();
      }
    });

  const onOpenRecent = (candidateId: string) => act('Opening…', () => open(candidateId, null));

  const locked = busy !== null;
  return (
    <div className="app">
      {api.mode === 'synthetic' && (
        <div className="synthetic-banner" role="status">
          Synthetic mode. Nothing on this page is evidence: no model ran and Atlas was not contacted.
        </div>
      )}
      <Header health={health} active={active} />
      {error && (
        <div className="notice notice-error" role="alert">
          <span>{error}</span>
          <button type="button" className="text-button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      <div className="notice notice-busy" role="status" aria-live="polite" hidden={!busy}>{busy}</div>
      <main className="bench">
        <IntakePanel
          source={source}
          intakeNote={intakeNote}
          candidate={candidate}
          recent={recent}
          locked={locked}
          onUpload={onUpload}
          onStage={onStage}
          onRevise={onRevise}
          onOpenRecent={onOpenRecent}
          onError={setError}
        />
        <EvidencePanel candidate={candidate} run={run} voiceReady={health?.voice.status === 'ready'} locked={locked} onRun={onRun} />
        <DecisionPanel candidate={candidate} run={run} locked={locked} onApprove={onApprove} onQuarantine={onQuarantine} />
      </main>
      <Footer history={history} active={active} run={run} health={health} />
    </div>
  );
}
