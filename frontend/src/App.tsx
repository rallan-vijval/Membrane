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
import { DecisionPanel, Footer, Header, RunPanel, SourcePanel } from './components';
import { ActiveTaskPanel, MemoryPanel } from './governed';
import { describeError } from './util';
import { UseProgress, QuickTest } from './SimpleUse';
import { Dashboard, type DashboardPanel } from './Dashboard';
import './workspace.css';
import { ScopeExperimentPanel } from './features/memory-lab/ScopeExperimentPanel';

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

function workspaceRoute() {
  const params = new URLSearchParams(window.location.search);
  const panel = params.get('panel');
  return { view: (params.get('page') === 'dashboard' || (!params.has('page') && params.has('execution')) ? 'dashboard' : 'use') as 'use' | 'dashboard',
    panel: (['overview', 'evidence', 'experiments', 'memory'].includes(panel ?? '') ? panel : params.has('execution') ? 'memory' : 'overview') as DashboardPanel };
}

export function App() {
  const [view, setView] = useState(workspaceRoute().view);
  const [dashboardPanel, setDashboardPanel] = useState<DashboardPanel>(workspaceRoute().panel);
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

  const navigate = (next: 'use' | 'dashboard', panel: DashboardPanel = dashboardPanel) => {
    setView(next); setDashboardPanel(panel);
    const url = new URL(window.location.href);
    url.searchParams.set('page', next);
    if (next === 'dashboard') url.searchParams.set('panel', panel);
    else url.searchParams.delete('panel');
    window.history.pushState(null, '', url);
  };
  useEffect(() => {
    const onPop = () => {
      const next = workspaceRoute(); setView(next.view); setDashboardPanel(next.panel);
      const p = new URLSearchParams(window.location.search);
      if ((p.get('candidate') ?? null) !== (candidate?.id ?? null) || (p.get('run') ?? null) !== (run?.id ?? null)) window.location.reload();
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [candidate?.id, run?.id]);
  const selectSaved = (id: string) => void act('Loading saved evidence...', async () => {
    const next = await api.getCandidate(id);
    const [nextSource, nextRun] = await Promise.all([api.getSource(next.source_id), next.latest_run_id ? api.getRun(next.latest_run_id) : Promise.resolve(null)]);
    if (nextRun && nextRun.candidate_id !== next.id) throw new Error('Saved run belongs to another proposal.');
    setSource(nextSource); setCandidate(next); setRun(nextRun);
  });

  return (
    <div className="app">
      {api.mode === 'synthetic' && <div className="synthetic-banner" role="status">SYNTHETIC MODE: nothing on this page is real evidence. No model ran and Atlas was not contacted.</div>}
      <Header health={health} active={active} compact={view === 'use'} />
      <nav className="workspace-tabs" aria-label="Workspace">
        <button type="button" aria-pressed={view === 'use'} onClick={() => navigate('use')}>Upload and test</button>
        <button type="button" aria-pressed={view === 'dashboard'} onClick={() => navigate('dashboard')}>Dashboard</button>
      </nav>
      {error && <div className="error" role="alert"><span>{error}</span><button type="button" className="link" onClick={() => setError(null)}>Dismiss</button></div>}
      {busy && <div className="busy" role="status">{busy}</div>}
      <main className="use-shell" hidden={view !== 'use'} aria-label="Upload and test workspace">
        <UseProgress source={source} candidate={candidate} run={run} />
        <SourcePanel source={source} candidate={candidate} disabled={busy !== null || view !== 'use'} onUpload={onUpload}
          onAudioSource={s => { setSource(s); setCandidate(null); setRun(null); }} onStage={onStage} onRevise={onRevise} />
        <QuickTest candidate={candidate} run={run} disabled={busy !== null} onRun={onRun} onDetails={() => navigate('dashboard', 'evidence')} />
        {run && runDone && <DecisionPanel candidate={candidate} run={run} disabled={busy !== null} onApprove={onApprove} onQuarantine={onQuarantine} />}
      </main>
      <Dashboard visible={view === 'dashboard'} panel={dashboardPanel} onPanel={panel => navigate('dashboard', panel)} candidate={candidate} run={run}
        history={history} memory={memory} health={health} onSelectCandidate={selectSaved} onUse={() => navigate('use')}
        evidence={<><RunPanel candidate={candidate} run={run} voice={health?.voice ?? null} disabled={busy !== null} onRun={onRun} /><Footer history={history} active={active} run={run} mode={api.mode} /></>}
        experiments={<ScopeExperimentPanel candidate={candidate} baseVersionId={active?.version_id ?? null} disabled={busy !== null} />}
        memoryTools={<div className="memory-workspace"><MemoryPanel memory={memory} problem={memoryProblem} disabled={busy !== null} onRevoke={onRevoke} onRefresh={() => void refreshShared()} />
          <details className="dashboard-disclosure" open={new URLSearchParams(window.location.search).has('execution') ? true : undefined}><summary>Try the current AI</summary><ActiveTaskPanel versionId={memory?.version_id ?? active?.version_id ?? null} disabled={busy !== null} onStale={() => void refreshShared()} /></details></div>} />
    </div>
  );
}
