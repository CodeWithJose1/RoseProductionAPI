import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

const ToastContext = createContext(null);

const ICONS = { success: CheckCircle2, error: AlertTriangle, info: Info };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const counter = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((items) => items.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback((type, message, timeout = type === 'error' ? 7000 : 4000) => {
    const id = ++counter.current;
    setToasts((items) => [...items.slice(-3), { id, type, message }]);
    if (timeout) setTimeout(() => dismiss(id), timeout);
    return id;
  }, [dismiss]);

  const value = useMemo(() => ({
    success: (message) => push('success', message),
    error: (message) => push('error', message),
    info: (message) => push('info', message),
    dismiss,
  }), [push, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type] || Info;
          return (
            <div key={toast.id} className={`toast toast-${toast.type}`} role={toast.type === 'error' ? 'alert' : 'status'}>
              <Icon size={18} aria-hidden="true" />
              <span className="toast-message">{toast.message}</span>
              <button type="button" className="icon-button" onClick={() => dismiss(toast.id)} aria-label="Dismiss notification">
                <X size={16} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside ToastProvider');
  return context;
}
