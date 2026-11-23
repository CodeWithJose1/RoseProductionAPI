import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';

export function Spinner({ size = 18, label }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <Loader2 size={size} className="spin" aria-hidden="true" />
      {label ? <span>{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

export function LoadingState({ label = 'Loading data…' }) {
  return (
    <div className="state-box">
      <Spinner size={28} label={label} />
    </div>
  );
}

export function EmptyState({ title = 'No records yet', message, action, icon: Icon = Inbox }) {
  return (
    <div className="state-box empty-state">
      <Icon size={36} aria-hidden="true" />
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = 'Could not load data' }) {
  return (
    <div className="state-box error-state" role="alert">
      <AlertTriangle size={32} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{error?.message || 'Unexpected error'}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          <RefreshCw size={16} aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}

export function InlineError({ error }) {
  if (!error) return null;
  const details = error.details && typeof error.details === 'object'
    ? Object.entries(error.details).filter(([, v]) => typeof v === 'string')
    : [];
  return (
    <div className="inline-error" role="alert">
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <strong>{error.message}</strong>
        {details.length > 0 && (
          <ul>
            {details.map(([field, message]) => (
              <li key={field}><code>{field}</code> {message}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
