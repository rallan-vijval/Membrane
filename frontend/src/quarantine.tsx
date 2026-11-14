/** Read-only quarantine shelf; caller supplies the bounded backend list. */
import type { Candidate } from './api';
import { scopeLabel } from './components';
export function QuarantineBox({ items, truncated, error, currentId, onOpen }: { items: Candidate[] | null; truncated: boolean; error: string | null; currentId: string | null; onOpen: (id: string) => void }) {
  const held = items?.filter(c => c.state === 'quarantined') ?? [];
  return <section className="panel quarantine-box" aria-labelledby="quarantine-h"><div className="quarantine-head"><h2 id="quarantine-h">Quarantine vault</h2><span className="quarantine-count">{items ? held.length : '—'}</span></div><p className="quarantine-sub">Rejected proposals stay outside active memory.</p>
    {error && <p role="status">Quarantine records unavailable.</p>}{!items && !error && <p>Loading...</p>}{items && held.length === 0 && <p className="empty">No rejected memories in the loaded list.</p>}{truncated && <p className="meta">Partial list; not a workspace total.</p>}
    <ul className="quarantine-list">{held.map(c => <li key={c.id} className={c.id === currentId ? 'held held-current' : 'held'}><p className="held-text">{c.text}</p><p className="meta">{scopeLabel(c.scope)}</p><button type="button" className="link" onClick={() => onOpen(c.id)}>Inspect this memory</button></li>)}</ul>
  </section>;
}
