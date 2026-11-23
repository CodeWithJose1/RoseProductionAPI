import { useId } from 'react';

/**
 * Label + control + hint/error. `children` receives the generated id and
 * aria props so the control is correctly associated with its label/error.
 */
export function FormField({ label, error, hint, required, children }) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`form-field${error ? ' has-error' : ''}`}>
      <label htmlFor={id}>
        {label}
        {required && <span className="required" aria-hidden="true"> *</span>}
      </label>
      {children({ id, 'aria-invalid': error ? 'true' : undefined, 'aria-describedby': describedBy })}
      {hint && !error && <p id={hintId} className="field-hint">{hint}</p>}
      {error && <p id={errorId} className="field-error" role="alert">{error}</p>}
    </div>
  );
}

export function TextInput({ label, value, onChange, error, hint, required, type = 'text', ...rest }) {
  return (
    <FormField label={label} error={error} hint={hint} required={required}>
      {(aria) => (
        <input
          {...aria}
          {...rest}
          type={type}
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </FormField>
  );
}

export function SelectInput({ label, value, onChange, options, error, hint, required, placeholder = 'Select…', ...rest }) {
  return (
    <FormField label={label} error={error} hint={hint} required={required}>
      {(aria) => (
        <select {...aria} {...rest} value={value ?? ''} onChange={(event) => onChange(event.target.value)}>
          <option value="">{placeholder}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      )}
    </FormField>
  );
}
