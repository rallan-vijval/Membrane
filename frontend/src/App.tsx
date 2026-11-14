import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  TERMINAL_RUN,
  type ActiveMemory,
  type Candidate,
  type Health,
  type History,
  type Run,
  type Scope,
  type Source,
} from './api';
import { DecisionPanel, Footer, Header, RunPanel, SourcePanel } from './components';
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
  const [active, setActive] = useState<ActiveMemory | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const alive = useRef(true);

  const fail = useCallback((err: unknown) => {
    if (alive.current) setError(describeError(err));
  }, []);

  /** Server state is the only authority on active memory: always re-read, never infer. */
  const refreshShared = useCallback(async () => {
    const [h, a, hist] = await Promise.allSettled([api.health(), api.activeMemory(), api.history()]);
    if (!alive.current) return;
    if (h.status === 'fulfilled') setHealth(h.value);
    if (a.status === 'fulfilled') setActive(a.value);
    if (hist.status === 'fulfilled') setHistory(hist.value);
    const firstFailure = [h, a, hist].find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
    if (firstFailure) fail(firstFailure.reason);
  }, [fail]);

  // Initial load, including a reload with ?candidate=…&run=… in the URL.
  useEffect(() => {
    alive.current = true;
    const url = readUrl();
    void (async () => {
      await refreshShared();
      try {
        if (url.candidate) {
          const c = await api.getCandidate(url.candidate);
          if (!alive.current) return;
          setCandidate(c);
          api.getSource(c.source_id).then((s) => alive.current && setSource(s)).catch(fail);
          const runId = url.run ?? c.latest_run_id;
          if (runId) {
            const r = await api.getRun(runId);
            if (r.candidate_id !== c.id) throw new Error('Selected run belongs to another candidate.');
            if (alive.current) setRun(r);
          }
        }
      } catch (err) {
        fail(err);
      } finally {
        if (alive.current) setHydrated(true);
      }
    })();
    return () => {
      alive.current = false;
    };
  }, [refreshShared, fail]);

  useEffect(() => {
    if (hydrated) writeUrl(candidate?.id ?? null, run?.id ?? null);
  }, [hydrated, candidate?.id, run?.id]);

  // Poll a run every two seconds until it reaches a terminal status or the page goes away.
  const runId = run?.id ?? null;
  const runDone = run ? TERMINAL_RUN.has(run.status) : true;
  useEffect(() => {
    if (!runId || runDone) return;
    let stopped = false;
    let timer: number;
    const tick = async () => {
      try {
        const next = await api.getRun(runId);
        // On the final poll read the candidate first: setting a terminal run ends this effect,
        // and the candidate's new state (eligible/quarantined) would otherwise be dropped.
        const c = TERMINAL_RUN.has(next.status) ? await api.getCandidate(next.candidate_id) : null;
        if (stopped) return;
        if (c) setCandidate(c);
        setRun(next);
      } catch (err) {
        if (!stopped) fail(err);
      } finally {
        if (!stopped) timer = window.setTimeout(() => void tick(), POLL_MS);
      }
    };
    timer = window.setTimeout(() => void tick(), POLL_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
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

  const onUpload = (file: File) =>
    act('Reading screenshot…', async () => {
      const s = await api.uploadSource(file);
      setSource(s);
      setCandidate(null);
      setRun(null);
    });

  const onStage = (text: string, scope: Scope) =>
    act('Staging…', async () => {
      if (!source || !active) throw new Error('Upload a source first.');
      const c = await api.createCandidate({ source_id: source.id, text, scope, base_version_id: active.version_id });
      setCandidate(c);
      setRun(null);
    });

  const onRevise = (text: string, scope: Scope) =>
    act('Creating revision…', async () => {
      if (!candidate) return;
      const child = await api.revise(candidate.id, { text, scope });
      setCandidate(child);
      setRun(null);
      await refreshShared();
    });

  const onRun = () =>
    act('Starting run…', async () => {
      if (!candidate) return;
      const { run_id } = await api.startRun(candidate.id);
      const [r, c] = await Promise.all([api.getRun(run_id), api.getCandidate(candidate.id)]);
      setRun(r);
      setCandidate(c);
    });

  const onApprove = () =>
    act('Approving…', async () => {
      if (!candidate || !run) return;
      try {
        setCandidate(await api.approve(candidate.id, run.id));
      } finally {
        await refreshShared();
      }
    });

  const onQuarantine = (reason: string) =>
    act('Quarantining…', async () => {
      if (!candidate) return;
      setCandidate(await api.quarantine(candidate.id, reason));
      await refreshShared();
    });

  return (
    <div className="app">
      {api.mode === 'synthetic' && (
        <div className="synthetic-banner" role="status">
          SYNTHETIC MODE: nothing on this page is real evidence. No model ran and Atlas was not contacted.
        </div>
      )}
      <Header health={health} active={active} />
      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button type="button" className="link" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {busy && <div className="busy" role="status">{busy}</div>}
      <main className="columns">
        <SourcePanel
          source={source}
          candidate={candidate}
          disabled={busy !== null}
          onUpload={onUpload}
          onStage={onStage}
          onRevise={onRevise}
        />
        <RunPanel candidate={candidate} run={run} voice={health?.voice ?? null} disabled={busy !== null} onRun={onRun} />
        <DecisionPanel candidate={candidate} run={run} disabled={busy !== null} onApprove={onApprove} onQuarantine={onQuarantine} />
      </main>
      <Footer history={history} active={active} run={run} mode={api.mode} />
    </div>
  );
}
