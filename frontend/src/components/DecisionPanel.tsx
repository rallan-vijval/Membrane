import { useState } from 'react';
import type { Candidate, Classification, Run } from '../api';
import { Status } from './Chrome';

interface Props {
  candidate: Candidate | null;
  run: Run | null;
  locked: boolean;
  onApprove: (reason: string) => void;
  onQuarantine: (reason: string) => void;
}

const COUNT_LABEL: [Classification, string][] = [
  ['new-policy-violation', 'break policy'],
  ['intended-safe-change', 'changed as intended'],
  ['unchanged-safe', 'unchanged'],
  ['pre-existing-violation', 'were already broken'],
  ['inconclusive', 'lack evidence'],
];

export function DecisionPanel({ candidate, run, locked, onApprove, onQuarantine }: Props) {
  const [reason, setReason] = useState('');
  const sameCandidate = candidate !== null && run !== null && run.candidate_id === candidate.candidate_id;
  // Approval is offered only when the BACKEND says this candidate and this exact run are eligible.
  const eligible = sameCandidate && candidate.status === 'eligible' && run.admission === 'eligible';
  const closed = candidate?.status === 'approved' || candidate?.status === 'quarantined';
  const admission = sameCandidate ? run.admission : null;
  const counts = sameCandidate ? COUNT_LABEL.map(([cls, label]) => [run.cases.filter((c) => c.classification === cls).length, label] as const).filter(([n]) => n > 0) : [];

  return (
    <section className="panel panel-decision" aria-labelledby="decision-h">
      <h2 id="decision-h"><span className="step">3</span> Your call</h2>
      {!candidate && <p className="empty">Nothing to decide yet.</p>}
      {candidate && (
        <>
          {admission === 'eligible' && (
            <div className="finding finding-eligible">
              <strong>✓ Safe to approve</strong>
              <p>Every replay finished and nothing broke policy. The memory only takes effect if you approve it.</p>
            </div>
          )}
          {admission === 'quarantine' && (
            <div className="finding finding-quarantine">
              <strong>✕ Keep it out</strong>
              <p>With this memory the agent tried something policy forbids. Quarantine it, or narrow it on the left and preview again.</p>
            </div>
          )}
          {admission === 'inconclusive' && (
            <div className="finding finding-inconclusive">
              <strong>? Not enough evidence</strong>
              <p>Some replays failed or did not finish. Run the preview again before deciding.</p>
            </div>
          )}
          {!admission && !closed && <p className="quiet">Run the preview to get a recommendation.</p>}

          {counts.length > 0 && (
            <p className="tally">Of {run?.cases.length} requests: {counts.map(([n, label]) => `${n} ${label}`).join(', ')}.</p>
          )}
          {sameCandidate && run.reasons.length > 0 && <ul className="reasons">{run.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}

          {closed ? (
            <p className="closed"><Status value={candidate.status} /> This candidate is closed. {candidate.status === 'approved' ? 'It is part of active memory now.' : 'It can never become active. Save a revision to try a narrower version.'}</p>
          ) : (
            <>
              <label className="field">
                <span>Reason for the record</span>
                <input value={reason} disabled={locked} onChange={(e) => setReason(e.target.value)}
                       placeholder={eligible ? 'Scoped to order 4821, matches the exception on file' : 'Waives returns for every VIP'} />
              </label>
              <div className="button-stack">
                <button type="button" className="approve" disabled={locked || !eligible || reason.trim().length === 0} onClick={() => onApprove(reason.trim())}>
                  Approve and activate
                </button>
                <button type="button" className="danger" disabled={locked || reason.trim().length === 0} onClick={() => onQuarantine(reason.trim())}>
                  Quarantine
                </button>
              </div>
              <p className="quiet">
                {eligible
                  ? 'Both decisions are recorded with your reason and the exact preview they rest on.'
                  : 'Approve unlocks only when the backend reports a passing preview for this exact candidate. There is no override.'}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
