import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { onUnauthorized } from '../api/client.js';
import { authApi } from '../api/endpoints.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // status: 'checking' | 'authenticated' | 'anonymous' | 'error'
  const [status, setStatus] = useState('checking');
  const [message, setMessage] = useState(null);
  const [configured, setConfigured] = useState(true);

  const check = useCallback(async () => {
    setStatus('checking');
    try {
      const result = await authApi.status();
      setConfigured(result.auth_configured !== false);
      setStatus(result.authenticated ? 'authenticated' : 'anonymous');
      setMessage(null);
    } catch (error) {
      setStatus('error');
      setMessage(error.message);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  useEffect(() => onUnauthorized(() => {
    setStatus('anonymous');
    setMessage('Your session has expired. Please sign in again.');
  }), []);

  const login = useCallback(async (apiKey) => {
    await authApi.login(apiKey);
    setMessage(null);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setMessage(null);
      setStatus('anonymous');
    }
  }, []);

  const value = useMemo(
    () => ({ status, message, configured, login, logout, recheck: check }),
    [status, message, configured, login, logout, check],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
