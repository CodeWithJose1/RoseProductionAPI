import { useState } from 'react';
import { Flower2, KeyRound, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import { InlineError, Spinner } from '../components/States.jsx';

export default function Login() {
  const { login, message, configured } = useAuth();
  const [key, setKey] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!key.trim()) {
      setError({ message: 'Enter the access key to continue.' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(key.trim());
    } catch (err) {
      setError(err);
    } finally {
      setKey('');
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <span className="brand-mark large" aria-hidden="true"><Flower2 size={28} /></span>
          <h1>Rose Production</h1>
          <p className="muted">Management and Forecasting System</p>
        </div>
        {!configured && (
          <InlineError error={{ message: 'The server has no API_KEY configured. Set it in the backend .env file.' }} />
        )}
        {message && !error && <p className="notice">{message}</p>}
        <form onSubmit={submit} noValidate>
          <div className="form-field">
            <label htmlFor="access-key">Access key</label>
            <div className="input-icon">
              <KeyRound size={16} aria-hidden="true" />
              <input
                id="access-key"
                type="password"
                autoComplete="current-password"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                placeholder="API key configured on the server"
              />
            </div>
          </div>
          {error && <InlineError error={error} />}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? <Spinner size={16} /> : null} Sign in
          </button>
        </form>
        <p className="login-footnote">
          <ShieldCheck size={14} aria-hidden="true" />
          The key is checked by the server and exchanged for a secure session cookie; it is never stored in the browser.
        </p>
      </div>
    </div>
  );
}
