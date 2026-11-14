import { api, type ComponentHealth, type Health, type History, type Run, type Version } from '../api';
import { clock, num, scopeLabel } from '../util';

const GLYPH: Record<string, string> = {
  ready: '●', unavailable: '✕', degraded: '▲', disabled: '○',
  eligible: '✓', approved: '✓', completed: '✓', quarantined: '✕', quarantine: '✕', failed: '✕',
  inconclusive: '?', staged: '○', testing: '◐', queued: '◐', running: '◐',
};

/** A status is always a glyph plus a word, never color alone. */
export function Status({ value, label }: { value: string; label?: string }) {
  return (
    <span className={`status status-${value}`}>
      <span aria-hidden="true">{GLYPH[value] ?? '•'}</span> {label ?? value}
    </span>
  );
}

function Light({ name, item }: { name: string; item: ComponentHealth | undefined }) {
  const status = item?.status ?? 'unavailable';
  return (
    <li title={item?.reason || undefined}>
      <span className="light-name">{name}</span>
      <Status value={status} />
    </li>
  );
}

export function Header({ health, active }: { health: Health | null; active: Version | null }) {
  return (
    <header className="masthead">
      <div className="brand">
        <h1>Membrane</h1>
        <p>See what a new memory will make your agent do, before it does it.</p>
      </div>
      <div className="masthead-side">
        <p className="active-memory">
          {active ? (
            <>The agent is running on <strong>{active.version_id}</strong> with {active.memories.length} {active.memories.length === 1 ? 'memory' : 'memories'}.</>
          ) : (
            'Active memory is not loaded.'
          )}
        </p>
        <ul className="lights" aria-label="Integration status">
          <Light name="Atlas" item={health?.database} />
          <Light name="Model" item={health?.model} />
          <Light name="Vector Search" item={health?.search} />
          <Light name="Voice" item={health?.voice} />
        </ul>
      </div>
    </header>
  );
}

export function Footer({ history, active, run, health }: { history: History | null; active: Version | null; run: Run | null; health: Health | null }) {
  const evidence = api.mode === 'synthetic' ? 'synthetic' : run?.live === false ? 'recorded' : 'live';
  return (
    <footer className="ledger">
      <details>
        <summary>Record: memory in force, version history, reviewer decisions, run details</summary>
        <div className="ledger-grid">
          <section>
            <h3>Memory in force</h3>
            {active && active.memories.length > 0 ? (
              <ul className="plain">
                {active.memories.map((m, i) => (
                  <li key={`${m.candidate_id ?? 'seed'}-${i}`}>
                    {m.text ?? '(no text)'}
                    <div className="quiet">{scopeLabel(m.scope)}{m.candidate_id ? `, from ${m.candidate_id}` : ', seeded policy'}</div>
                  </li>
                ))}
              </ul>
            ) : <p className="quiet">Nothing loaded.</p>}
          </section>
          <section>
            <h3>Versions</h3>
            {history && history.versions.length > 0 ? (
              <ol className="plain">
                {history.versions.map((v) => (
                  <li key={v.version_id}>
                    <code>{v.version_id}</code> at {clock(v.created_at)}
                    {v.candidate_id && <div className="quiet">activated by {v.candidate_id}, evidence {v.run_id}</div>}
                  </li>
                ))}
              </ol>
            ) : <p className="quiet">No versions loaded.</p>}
          </section>
          <section>
            <h3>Reviewer decisions</h3>
            {history && history.events.length > 0 ? (
              <ol className="plain">
                {history.events.map((e) => (
                  <li key={e.event_id}>
                    <Status value={e.decision === 'approve' ? 'approved' : e.decision === 'quarantine' ? 'quarantined' : 'staged'} label={e.decision} /> <code>{e.candidate_id}</code> at {clock(e.created_at)}
                    <div className="quiet">{e.actor} (demo identity){e.reason ? `: ${e.reason}` : ''}</div>
                  </li>
                ))}
              </ol>
            ) : <p className="quiet">No decisions yet.</p>}
            {history?.truncated && <p className="quiet">Showing the latest 100.</p>}
          </section>
          <section>
            <h3>This run</h3>
            {run ? (
              <dl className="facts">
                <dt>Run</dt><dd><code>{run.run_id}</code> <span className={`evidence-tag evidence-${evidence}`}>{evidence} evidence</span></dd>
                <dt>Model</dt><dd>{Object.entries(run.config).filter(([, v]) => typeof v === 'string' || typeof v === 'number').slice(0, 4).map(([k, v]) => `${k}: ${String(v)}`).join(', ') || 'not reported'}</dd>
                <dt>Usage</dt><dd>{num(run.usage['model_calls'] ?? run.usage['calls'])} model calls, {num(run.usage['input_tokens']) + num(run.usage['output_tokens'])} tokens, {(num(run.usage['elapsed_ms'] ?? run.usage['latency_ms']) / 1000).toFixed(1)} s</dd>
                <dt>Tested against</dt><dd><code>{run.base_version_id}</code></dd>
              </dl>
            ) : <p className="quiet">No run open.</p>}
            {health?.workspace_id && <p className="quiet">Workspace {health.workspace_id}</p>}
          </section>
        </div>
      </details>
    </footer>
  );
}
