// Client-side validation mirroring the API/database rules. The server
// re-validates everything; these checks only give immediate feedback.

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function isValidDate(value) {
  if (!ISO_DATE.test(value || '')) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export const rules = {
  required: (label) => (value) =>
    value === undefined || value === null || String(value).trim() === ''
      ? `${label} is required`
      : null,
  maxLength: (label, max) => (value) =>
    value && String(value).trim().length > max ? `${label} must be at most ${max} characters` : null,
  date: (label) => (value) => (value && !isValidDate(value) ? `${label} must be a valid date` : null),
  positiveInteger: (label) => (value) => {
    if (value === '' || value === null || value === undefined) return null;
    const number = Number(value);
    if (!Number.isInteger(number)) return `${label} must be a whole number`;
    if (number <= 0) return `${label} must be greater than zero`;
    if (number > 2147483647) return `${label} is too large`;
    return null;
  },
  positiveNumber: (label, max) => (value) => {
    if (value === '' || value === null || value === undefined) return null;
    const number = Number(value);
    if (!Number.isFinite(number)) return `${label} must be a number`;
    if (number <= 0) return `${label} must be greater than zero`;
    if (max !== undefined && number > max) return `${label} must be at most ${max}`;
    return null;
  },
  nonNegativeNumber: (label, max) => (value) => {
    if (value === '' || value === null || value === undefined) return null;
    const number = Number(value);
    if (!Number.isFinite(number)) return `${label} must be a number`;
    if (number < 0) return `${label} cannot be negative`;
    if (max !== undefined && number > max) return `${label} must be at most ${max}`;
    return null;
  },
};

/** Run { field: [rule, ...] } over values; returns { field: message }. */
export function runRules(values, schema) {
  const errors = {};
  Object.entries(schema).forEach(([field, fieldRules]) => {
    for (const rule of fieldRules) {
      const message = rule(values[field], values);
      if (message) {
        errors[field] = message;
        break;
      }
    }
  });
  return errors;
}

export function dateWithin(value, start, end) {
  return Boolean(value && start && end && value >= start && value <= end);
}

// ---------------------------------------------------------------------------
// Duplicate hints. The API (and the database UNIQUE constraints) are the
// authoritative check; these only give immediate feedback with the rows that
// the page has already loaded.

/** Text as the API stores it: trimmed, internal spaces collapsed. */
export const normalizeText = (value) => String(value ?? '').trim().replace(/\s+/g, ' ');

/** Identity key of a text value: normalized and case-insensitive. */
export const textKey = (value) => normalizeText(value).toLowerCase();

/**
 * Find another loaded row with the same identity.
 * - rows: loaded records; idKey: their primary-key field
 * - editing: the record being edited (or null when creating)
 * - sameAs(row): true when row has the identity being entered
 * - unchanged: true when an edited record keeps its own identity (always
 *   allowed, so pre-existing duplicates stay editable)
 */
export function findClash({ rows, idKey, editing, sameAs, unchanged = false }) {
  if (!rows || (editing && unchanged)) return null;
  return rows.find((row) => (!editing || row[idKey] !== editing[idKey]) && sameAs(row)) || null;
}

/** Add a duplicate message to errors unless the field already has one. */
export function withDuplicate(errors, field, clash, message) {
  if (clash && !errors[field]) return { ...errors, [field]: message };
  return errors;
}
