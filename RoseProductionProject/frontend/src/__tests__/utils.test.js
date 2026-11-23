import { describe, expect, it } from 'vitest';
import { dateWithin, isValidDate, rules, runRules } from '../utils/validation.js';
import { formatDate, formatInt, seasonStatus, swatchFor } from '../utils/format.js';

describe('validation rules', () => {
  it('validates ISO dates strictly', () => {
    expect(isValidDate('2026-02-14')).toBe(true);
    expect(isValidDate('2026-02-30')).toBe(false);
    expect(isValidDate('14/02/2026')).toBe(false);
  });

  it('checks positive integers like Harvest.quantity', () => {
    const rule = rules.positiveInteger('Quantity');
    expect(rule('10')).toBeNull();
    expect(rule('0')).toMatch(/greater than zero/);
    expect(rule('-3')).toMatch(/greater than zero/);
    expect(rule('1.5')).toMatch(/whole number/);
  });

  it('checks non-negative numbers like Forecast.estimated_quantity', () => {
    const rule = rules.nonNegativeNumber('Estimate');
    expect(rule('0')).toBeNull();
    expect(rule('-1')).toMatch(/cannot be negative/);
  });

  it('runs the first failing rule per field', () => {
    const errors = runRules({ name: '', color: 'x'.repeat(60) }, {
      name: [rules.required('Name')],
      color: [rules.required('Color'), rules.maxLength('Color', 50)],
    });
    expect(errors).toEqual({ name: 'Name is required', color: 'Color must be at most 50 characters' });
  });

  it('checks a date is inside a season range', () => {
    expect(dateWithin('2026-02-10', '2026-02-01', '2026-02-14')).toBe(true);
    expect(dateWithin('2026-03-01', '2026-02-01', '2026-02-14')).toBe(false);
  });
});

describe('formatting', () => {
  it('formats numbers and dates', () => {
    expect(formatInt(10900)).toBe('10,900');
    expect(formatInt(null)).toBe('—');
    expect(formatDate('2026-02-14')).toBe('Feb 14, 2026');
  });

  it('derives season status from dates', () => {
    const season = { start_date: '2026-02-01', end_date: '2026-02-14' };
    expect(seasonStatus(season, '2026-01-01')).toBe('upcoming');
    expect(seasonStatus(season, '2026-02-05')).toBe('active');
    expect(seasonStatus(season, '2026-03-01')).toBe('past');
  });

  it('maps rose colour names to swatches', () => {
    expect(swatchFor('Red')).toMatch(/^#/);
    expect(swatchFor('Light pink')).toBe(swatchFor('pink'));
    expect(swatchFor('Unknown')).toBe('#d4d4d4');
  });
});
