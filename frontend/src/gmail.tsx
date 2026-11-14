import { useState } from 'react';
import { api, type GmailMessage, type GmailStatus } from './api';
import { describeError } from './util';

/**
 * Gmail as a source. Nothing is read until the reviewer searches, and only the email they pick
 * is imported. It becomes an untrusted source like any upload and must pass the same test.
 */
export function GmailPanel({ disabled, onImport }: { disabled: boolean; onImport: (kind: 'message' | 'thread', id: string) => void }) {
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<GmailMessage[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true);
    setProblem(null);
    try { await fn(); } catch (err) { setProblem(describeError(err)); } finally { setBusy(false); }
  };
  const connect = () => guard(async () => setStatus(await api.gmailStatus()));
  const search = () => guard(async () => setItems(await api.gmailSearch(query.trim())));

  return (
    <details className="gmail" onToggle={(e) => { if (e.currentTarget.open && !status) void connect(); }}>
      <summary>Or pick an email from Gmail</summary>
      {status?.status === 'ready' ? (
        <>
          <p className="meta">Connected read-only to {status.account}. Only the email you import is read.</p>
          <form className="gmail-search" onSubmit={(e) => { e.preventDefault(); void search(); }}>
            <label className="field">
              <span>Search Gmail</span>
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. refund exception" disabled={busy} />
            </label>
            <button type="submit" className="secondary" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
          </form>
          {items && items.length === 0 && <p className="empty">No emails match.</p>}
          {items && items.length > 0 && (
            <ul className="gmail-list">
              {items.map((m) => (
                <li key={m.message_id}>
                  <div className="gmail-subject">{m.subject || '(no subject)'}</div>
                  <div className="meta">{m.sender} · {m.date}</div>
                  <div className="gmail-snippet">{m.snippet}</div>
                  <div className="actions">
                    <button type="button" disabled={disabled} onClick={() => onImport('message', m.message_id)}>Import email</button>
                    <button type="button" className="secondary" disabled={disabled} onClick={() => onImport('thread', m.thread_id)}>Import whole thread</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : status ? (
        <p className="meta">Gmail is not connected: {status.detail}</p>
      ) : (
        <p className="meta">{busy ? 'Checking the Gmail connection…' : ''}</p>
      )}
      {problem && <p className="intake-problem" role="status">{problem}</p>}
    </details>
  );
}
