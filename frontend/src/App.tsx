import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  TERMINAL_RUN,
  type ActiveMemory,
  type GovernedMemory,
  type Candidate,
  type Health,
  type History,
  type Run,
  type Scope,
  type Source,
} from './api';
import { CandidateFacts, DecisionPanel, Footer, Header, RunPanel, SourcePanel } from './components';
import { ActiveTaskPanel, MemoryPanel } from './governed';
import { describeError } from './util';
import { QuarantineBox } from './quarantine';
import { ChangeHighlight, KeyPanel, verdictOf } from './summary';

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
  window.history.replaceState(window.history.state, '', `${query ? `?${query}` : window.location.pathname}${window.location.hash}`);
}

export function App() {
  const [view, setView] = useState<'review' | 'live'>(() => new URLSearchParams(window.location.search).has('execution') ? 'live' : 'review');
  const [health, setHealth] = useState<Health | null>(null);
  const [active, setActive] = useState<ActiveMemory | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [memory, setMemory] = useState<GovernedMemory | null>(null);
  const [memoryProblem, setMemoryProblem] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const alive = useRef(true);
  // The full breakdown is its own view at #breakdown, so the browser's Back button returns to the summary too.
  const [detail, setDetail] = useState(() => window.location.hash === '#breakdown');
  const openedHere = useRef(false);
  useEffect(() => {
    const sync = () => { setDetail(window.location.hash === '#breakdown'); window.scrollTo({ top: 0 }); };
    window.addEventListener('hashchange', sync);
    window.addEventListener('popstate', sync);
    return () => { window.removeEventListener('hashchange', sync); window.removeEventListener('popstate', sync); };
  }, []);
  const leaveBreakdown = useCallback(() => {
    if (window.location.hash !== '#breakdown') { setDetail(false); return; }
    if (openedHere.current) { openedHere.current = false; window.history.back(); return; }
    // Opened from a shared link or a reload: there is no summary entry to go back to, so replace this one.
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    setDetail(false);
    window.scrollTo({ top: 0 });
  }, []);
  const openBreakdown = () => {
    if (window.location.hash === '#breakdown') { setDetail(true); return; }
    openedHere.current = true;
    window.location.hash = 'breakdown';
  };

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
    // Governed entries are a newer endpoint: report trouble inside its own panel, not as a page error.
    try {
      const entries = await api.memoryEntries();
      if (alive.current) { setMemory(entries); setMemoryProblem(null); }
    } catch (err) {
      if (alive.current) { setMemory(null); setMemoryProblem(`Could not load governed memory: ${describeError(err)}`); }
    }
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

  // A breakdown needs a run. When the run goes away (new upload, revision), return to the summary.
  useEffect(() => {
    if (hydrated && !run && window.location.hash === '#breakdown') leaveBreakdown();
  }, [hydrated, run, leaveBreakdown]);

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

  const onStage = (text: string, scope: Scope, ttlSeconds: number) =>
    act('Staging…', async () => {
      if (!source || !active) throw new Error('Upload a source first.');
      const c = await api.createCandidate({ source_id: source.id, text, scope, base_version_id: active.version_id, ttl_seconds: ttlSeconds });
      setCandidate(c);
      setRun(null);
    });

  const onRevise = (text: string, scope: Scope, ttlSeconds: number) =>
    act('Creating revision…', async () => {
      if (!candidate) return;
      const child = await api.revise(candidate.id, { text, scope, ttl_seconds: ttlSeconds });
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

  const onRevoke = (memoryId: string, reason: string) =>
    act('Revoking…', async () => {
      if (!memory) return;
      try {
        // The base version makes a stale page fail with 409 instead of revoking against newer memory.
        await api.revokeMemory(memoryId, { base_version_id: memory.version_id, reason });
      } finally {
        await refreshShared();
      }
    });

  /** Open an earlier candidate with its latest evidence, e.g. from the quarantine box. */
  const onOpenCandidate = (candidateId: string) =>
    act('Opening…', async () => {
      const c = await api.getCandidate(candidateId);
      const r = c.latest_run_id ? await api.getRun(c.latest_run_id) : null;
      setCandidate(c);
      setRun(r);
      api.getSource(c.source_id).then((s) => alive.current && setSource(s)).catch(fail);
      window.scrollTo({ top: 0 });
    });

  const showBreakdown = detail && run !== null;
  const verdict = verdictOf(candidate, run);

  return (
    <div className="app">
      {api.mode === 'synthetic' && (
        <div className="synthetic-banner" role="status">
          SYNTHETIC MODE: nothing on this page is real evidence. No model ran and Atlas was not contacted.
        </div>
      )}
      <Header health={health} active={active} />
      <nav className="workspace-tabs" aria-label="Workspace">
        <button type="button" aria-pressed={view === 'review'} onClick={() => setView('review')}>Review a proposed memory</button>
        <button type="button" aria-pressed={view === 'live'} onClick={() => setView('live')}>Approved memories and current AI</button>
      </nav>
      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button type="button" className="link" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {busy && <div className="busy" role="status">{busy}</div>}
      {/* Kept mounted while the breakdown is open, so unsaved edits and open sections survive the round trip. */}
      {(
        <div role={showBreakdown ? undefined : 'main'} className="review-flow summary-flow" hidden={view !== 'review' || showBreakdown}>
          <SourcePanel
            source={source}
            candidate={candidate}
            disabled={busy !== null}
            onUpload={onUpload}
            onStage={onStage}
            onRevise={onRevise}
          />
          <KeyPanel candidate={candidate} run={run} disabled={busy !== null} onRun={onRun} onOpen={openBreakdown} />
          <ChangeHighlight run={run} />
          <DecisionPanel candidate={candidate} run={run} disabled={busy !== null} onApprove={onApprove} onQuarantine={onQuarantine} />
          <QuarantineBox refreshKey={`${candidate?.id ?? ''}:${candidate?.state ?? ''}:${run?.status ?? ''}`} currentId={candidate?.id ?? null} onOpen={onOpenCandidate} />
        </div>
      )}
      {showBreakdown && (
        <main className="review-flow breakdown" hidden={view !== 'review'} aria-label="Full breakdown">
          <div className={`breakdown-head key-${verdict.tone}`}>
            <button type="button" className="secondary back" onClick={leaveBreakdown}>
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 5l-7 7 7 7" /></svg>
              Back to summary
            </button>
            <p className="breakdown-verdict"><strong>{verdict.title}</strong> {verdict.line}</p>
          </div>
          <RunPanel candidate={candidate} run={run} voice={health?.voice ?? null} />
          {candidate && <CandidateFacts candidate={candidate} run={run} />}
        </main>
      )}
      <section hidden={view !== 'live'} aria-label="Approved memory workspace"><div className="live-divider"><span>AFTER THE CHECKPOINT</span><h2>Memory in use</h2><p>Inspect what is active, or try a single request. These live trials do not count as admission evidence.</p></div>
      <div className="governed">
        <MemoryPanel memory={memory} problem={memoryProblem} disabled={busy !== null} onRevoke={onRevoke} onRefresh={() => void refreshShared()} />
        <ActiveTaskPanel versionId={memory?.version_id ?? active?.version_id ?? null} disabled={busy !== null} onStale={() => void refreshShared()} />
      </div>
      </section>
      <Footer history={history} active={active} run={run} mode={api.mode} />
    </div>
  );
}
