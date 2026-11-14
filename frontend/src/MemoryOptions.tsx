import { useId } from 'react';
import type { Scope } from './api';

const choices = [
  { value: 'global', label: 'All orders', hint: 'Broad scope', path: 'M3 7h18M3 17h18M7 3v18M17 3v18' },
  { value: 'order', label: 'One order', hint: 'Order + customer', path: 'M8 3h8l4 4v14H4V3h4M8 11h8M8 15h5' },
  { value: 'preference', label: 'Preference', hint: 'Response guidance', path: 'M4 7h16M4 17h16M8 4v6M16 14v6' },
] as const;

export function ScopeChoices({ value, onChange, disabled }: { value: Scope['kind']; onChange: (value: Scope['kind']) => void; disabled: boolean }) {
  const name = useId();
  return <fieldset className="scope-choices" disabled={disabled}><legend>Where can this memory apply?</legend><div className="scope-cards">{choices.map(choice => <label className="scope-card" key={choice.value}>
    <input type="radio" name={name} value={choice.value} checked={value === choice.value} onChange={() => onChange(choice.value)} aria-label={choice.label}/>
    <svg aria-hidden="true" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={choice.path}/></svg>
    <strong>{choice.label}</strong><small>{choice.hint}</small>
  </label>)}</div></fieldset>;
}
