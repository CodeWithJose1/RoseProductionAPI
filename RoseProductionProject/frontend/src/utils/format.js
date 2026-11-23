const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });

export function formatInt(value) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? '—' : integer.format(value);
}

export function formatNumber(value) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? '—' : decimal.format(value);
}

export function formatCompact(value) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
});
const shortDateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', timeZone: 'UTC',
});

export function formatDate(iso) {
  if (!iso) return '—';
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? iso : dateFormatter.format(date);
}

export function formatShortDate(iso) {
  if (!iso) return '';
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? iso : shortDateFormatter.format(date);
}

export function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now - offset).toISOString().slice(0, 10);
}

export function seasonStatus(season, today = todayIso()) {
  if (!season) return 'unknown';
  if (season.end_date < today) return 'past';
  if (season.start_date > today) return 'upcoming';
  return 'active';
}

export function daysBetween(fromIso, toIso) {
  const from = new Date(`${fromIso}T00:00:00Z`);
  const to = new Date(`${toIso}T00:00:00Z`);
  return Math.round((to - from) / 86400000);
}

/** Map a rose colour name to a CSS swatch (display only). */
const NAMED = {
  red: '#c8102e', white: '#f8f8f4', pink: '#f4a6c1', yellow: '#f6d32d', orange: '#f28c28',
  purple: '#7b3fa0', lavender: '#b8a2d8', peach: '#f9b98f', coral: '#f47c64', cream: '#f3ead3',
  burgundy: '#7a1f3d', fuchsia: '#d6338a', salmon: '#f59a8a', bicolor: 'linear-gradient(135deg,#c8102e 50%,#f6d32d 50%)',
  green: '#6cae4f', blue: '#3a6fd8', champagne: '#f1ddb8', ivory: '#fbf6e6', magenta: '#c2185b',
};

export function swatchFor(colorName) {
  if (!colorName) return '#d4d4d4';
  const key = colorName.trim().toLowerCase();
  if (NAMED[key]) return NAMED[key];
  const firstWord = key.split(/[\s/-]+/).find((word) => NAMED[word]);
  if (firstWord) return NAMED[firstWord];
  if (/^#[0-9a-f]{3,8}$/i.test(key)) return key;
  return '#d4d4d4';
}
