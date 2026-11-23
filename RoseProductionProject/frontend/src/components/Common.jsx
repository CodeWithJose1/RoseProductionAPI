import { Pencil, Trash2 } from 'lucide-react';
import { swatchFor } from '../utils/format.js';

export function PageHeader({ title, description, icon: Icon, actions }) {
  return (
    <header className="page-header">
      <div className="page-title">
        {Icon && <span className="page-icon"><Icon size={22} aria-hidden="true" /></span>}
        <div>
          <h1>{title}</h1>
          {description && <p className="muted">{description}</p>}
        </div>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'default' }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {Icon && <span className="stat-icon"><Icon size={18} aria-hidden="true" /></span>}
      </div>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="stat-hint">{hint}</span>}
    </article>
  );
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function ColorSwatch({ color }) {
  const background = swatchFor(color);
  return (
    <span className="swatch-wrap">
      <span className="swatch" style={{ background }} aria-hidden="true" />
      {color}
    </span>
  );
}

export function RowActions({ onEdit, onDelete, label }) {
  return (
    <div className="row-actions">
      {onEdit && (
        <button type="button" className="icon-button" onClick={onEdit} aria-label={`Edit ${label}`} title="Edit">
          <Pencil size={16} />
        </button>
      )}
      {onDelete && (
        <button type="button" className="icon-button danger" onClick={onDelete} aria-label={`Delete ${label}`} title="Delete">
          <Trash2 size={16} />
        </button>
      )}
    </div>
  );
}

export function FilterBar({ children, onReset, active }) {
  return (
    <div className="filter-bar" role="group" aria-label="Filters">
      {children}
      {onReset && (
        <button type="button" className="btn btn-ghost" onClick={onReset} disabled={!active}>
          Clear filters
        </button>
      )}
    </div>
  );
}

export function FilterSelect({ label, value, onChange, options, allLabel = 'All' }) {
  return (
    <label className="filter-control">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

export function FilterDate({ label, value, onChange }) {
  return (
    <label className="filter-control">
      <span>{label}</span>
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
