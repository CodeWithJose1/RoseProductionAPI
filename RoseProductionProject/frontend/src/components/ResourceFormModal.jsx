import { useEffect, useRef, useState } from 'react';
import { Modal } from './Modal.jsx';
import { InlineError, Spinner } from './States.jsx';

/**
 * Generic create/edit dialog.
 * - validate(values) -> { field: message } (client-side rules)
 * - onSubmit(values) -> Promise (API call). ApiError.details are mapped onto
 *   the fields with the same name; other errors are shown as a banner.
 * - Only one submission can be in flight: a synchronous lock (ref) blocks a
 *   second submit even if it arrives before React re-renders the disabled
 *   button (double click, Enter + click, repeated requestSubmit). After an
 *   error the values stay in the form so the user can correct them.
 */
export function ResourceFormModal({
  open, title, description, initialValues, validate, onSubmit, onClose, renderFields,
  submitLabel = 'Save', size = 'md',
}) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    if (open) {
      setValues(initialValues);
      setErrors({});
      setServerError(null);
      setTouched(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = (field, value) => {
    setValues((current) => {
      const next = { ...current, [field]: value };
      if (touched && validate) setErrors(validate(next));
      return next;
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (inFlight.current) return; // a submission is already being processed
    setTouched(true);
    const clientErrors = validate ? validate(values) : {};
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;
    inFlight.current = true;
    setSubmitting(true);
    setServerError(null);
    try {
      await onSubmit(values);
    } catch (error) {
      const fieldErrors = {};
      if (error?.details && typeof error.details === 'object') {
        Object.entries(error.details).forEach(([field, message]) => {
          if (field in values && typeof message === 'string') fieldErrors[field] = message;
        });
      }
      setErrors(fieldErrors);
      setServerError(error);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={title}
      description={description}
      onClose={submitting ? undefined : onClose}
      size={size}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" form="resource-form" className="btn btn-primary" disabled={submitting} aria-busy={submitting}>
            {submitting ? <Spinner size={16} /> : null} {submitLabel}
          </button>
        </>
      )}
    >
      <form id="resource-form" className="form-grid" onSubmit={handleSubmit} noValidate>
        {serverError && <div className="form-span"><InlineError error={serverError} /></div>}
        {renderFields({ values, set, errors })}
      </form>
    </Modal>
  );
}
