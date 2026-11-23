import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import { Spinner } from './States.jsx';

export function Modal({ open, title, onClose, children, footer, size = 'md', description }) {
  const titleId = useId();
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    const onKey = (event) => {
      if (event.key === 'Escape') onCloseRef.current?.();
    };
    document.addEventListener('keydown', onKey);
    const focusable = dialogRef.current?.querySelector('input, select, textarea, button:not(.modal-close)');
    focusable?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose?.()}>
      <div
        ref={dialogRef}
        className={`modal modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="modal-header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p className="muted">{description}</p>}
          </div>
          <button type="button" className="icon-button modal-close" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({
  open, title = 'Are you sure?', message, confirmLabel = 'Delete', onConfirm, onCancel, busy, error,
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={busy ? undefined : onCancel}
      size="sm"
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? <Spinner size={16} /> : null} {confirmLabel}
          </button>
        </>
      )}
    >
      <div className="confirm-body">
        <AlertTriangle size={28} className="confirm-icon" aria-hidden="true" />
        <div>
          <p>{message}</p>
          {error && <p className="field-error" role="alert">{error}</p>}
        </div>
      </div>
    </Modal>
  );
}
