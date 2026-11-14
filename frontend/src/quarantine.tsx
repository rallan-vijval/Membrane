/**
 * The holding box: proposed memories the checks kept out of active memory.
 * A plain list read from the backend's candidates. Nothing here is decided in the browser.
 */
import { useEffect, useState } from 'react';
import { api, type Candidate } from './api';
import { scopeLabel } from './components';

interface Props {
  /** Changes whenever a candidate may have changed state, to re-read the list. */
  refreshKey: string;
  currentId: string | null;
  onOpen: (candidateId: string) => void;
}

export function QuarantineBox({ refreshKey, currentId, onOpen }: Props) {
  const [items, setItems] = useState<Candidate[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api.listCandidates().then((list) => { if (alive) { setItems(list); setFailed(false); } }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [refreshKey]);

  const held = (items ?? []).filter((c) => c.state === 'quarantined');
  const successor = (id: string) => (items ?? []).find((c) => c.parent_candidate_id === id);

  return (
    <section className="panel quarantine-box" aria-labelledby="quarantine-h">
      <div className="quarantine-head">
        <h2 id="quarantine-h">Quarantine</h2>
        <span className="quarantine-count" aria-label={`${held.length} held`}>{held.length}</span>
      </div>
      <p className="quarantine-sub">Held outside memory. The live agent never sees these.</p>
      {failed && <p className="meta">The list of rejected memories could not be loaded.</p>}
      {!failed && items && held.length === 0 && <p className="empty">Nothing is being held.</p>}
      <ul className="quarantine-list">
        {held.map((c) => {
          const next = successor(c.id);
          return (
            <li key={c.id} className={c.id === currentId ? 'held held-current' : 'held'}>
              <p className="held-text">{c.text}</p>
              <p className="meta">{scopeLabel(c.scope)} · <code>{c.id}</code></p>
              {next && (
                <p className="held-next">
                  Revised as <code>{next.id}</code>: <span className={`pill pill-${next.state}`}>{next.state}</span>
                </p>
              )}
              {c.id !== currentId && <button type="button" className="link" onClick={() => onOpen(c.id)}>Open its evidence</button>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
