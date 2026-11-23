// Duplicate prevention in the GUI (2026-11-23): one submission at a time,
// client-side duplicate hints, API 409 shown with the input preserved.
import { describe, expect, it } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockFetch, reply } from '../test/mockFetch.js';
import { renderApp } from '../test/renderApp.jsx';
import * as fx from '../test/fixtures.js';
import { findClash, normalizeText, textKey } from '../utils/validation.js';
import { validateVariety } from '../pages/Varieties.jsx';
import { validateLot } from '../pages/Lots.jsx';
import { validateFarm } from '../pages/Farms.jsx';
import { validateSeason } from '../pages/Seasons.jsx';
import { validateCrop } from '../pages/Crops.jsx';

function base(extra = {}) {
  return mockFetch({
    '/auth/status': { authenticated: true, auth_configured: true },
    '/farms': { count: 1, farms: fx.farms },
    '/lots': { count: 1, lots: fx.lots },
    '/varieties': { count: 2, varieties: fx.varieties },
    '/crops': { count: 1, crops: fx.crops },
    '/seasons': { count: 1, seasons: fx.seasons },
    '/harvests': { count: 1, harvests: fx.harvests },
    '/forecasts': { count: 0, forecasts: [] },
    '/forecasts/summary': { rows: [] },
    ...extra,
  });
}

const posts = (fetch, path) => fetch.calls.filter((c) => c.method === 'POST' && c.path === path);

describe('normalization helpers', () => {
  it('normalizes spacing and compares case-insensitively', () => {
    expect(normalizeText('  Lot    A ')).toBe('Lot A');
    expect(textKey('  QUICKSAND  ')).toBe(textKey('quicksand'));
    expect(findClash({ rows: [{ id: 1, n: 'a' }], idKey: 'id', editing: null, sameAs: (r) => r.n === 'a' })).toEqual({ id: 1, n: 'a' });
    expect(findClash({ rows: [{ id: 1, n: 'a' }], idKey: 'id', editing: { id: 1 }, sameAs: (r) => r.n === 'a' })).toBeNull();
  });
});

describe('client-side duplicate rules mirror the API rules', () => {
  const ctx = (rows, editing = null) => ({ rows, editing });

  it('variety: same name in any case/spacing is a duplicate; editing its own name is allowed', () => {
    expect(validateVariety({ name: '  freedom ', color: 'White' }, ctx(fx.varieties)).name)
      .toBe('A rose variety with this name already exists.');
    expect(validateVariety({ name: 'Freedom', color: 'Pink' }, ctx(fx.varieties, fx.varieties[0])).name).toBeUndefined();
    expect(validateVariety({ name: 'Vendela', color: 'Red' }, ctx(fx.varieties, fx.varieties[0])).name)
      .toBe('A rose variety with this name already exists.');
    expect(validateVariety({ name: 'Mondial', color: 'White' }, ctx(fx.varieties)).name).toBeUndefined();
  });

  it('lot: unique inside its farm only', () => {
    expect(validateLot({ farm_id: '1', name: 'lot  a', area: '2' }, ctx(fx.lots)).name)
      .toBe('This lot already exists in the selected farm.');
    expect(validateLot({ farm_id: '2', name: 'Lot A', area: '2' }, ctx(fx.lots)).name).toBeUndefined();
  });

  it('farm: same name and location is a duplicate, same name elsewhere is not', () => {
    expect(validateFarm({ name: 'FARM ONE', location: ' cayambe' }, ctx(fx.farms)).name)
      .toBe('A farm with this name already exists at this location.');
    expect(validateFarm({ name: 'Farm One', location: 'Tabacundo' }, ctx(fx.farms)).name).toBeUndefined();
  });

  it('season: same name with overlapping dates is a duplicate, next year is not', () => {
    expect(validateSeason({ name: 'valentines day 2026', start_date: '2026-02-10', end_date: '2026-02-20' }, ctx(fx.seasons)).name)
      .toBe('A season with this name already exists for an overlapping period.');
    expect(validateSeason({ name: 'Valentines Day 2026', start_date: '2027-02-01', end_date: '2027-02-14' }, ctx(fx.seasons)).name).toBeUndefined();
  });

  it('crop: same lot, variety and planting date is a duplicate; another date is a new crop cycle', () => {
    expect(validateCrop({ lot_id: '1', variety_id: '1', planting_date: '2024-03-01' }, ctx(fx.crops)).planting_date)
      .toBe('This variety is already planted in this lot on this date.');
    expect(validateCrop({ lot_id: '1', variety_id: '1', planting_date: '2025-03-01' }, ctx(fx.crops)).planting_date).toBeUndefined();
  });
});

describe('form submission', () => {
  it('sends only one POST when the submit button is activated twice before React re-renders', async () => {
    const user = userEvent.setup();
    let release;
    const fetch = base({
      'POST /varieties': () => new Promise((resolve) => { release = () => resolve(reply(201, { variety: { variety_id: 9, name: 'Mondial', color: 'White' } })); }),
    });
    renderApp('/varieties');
    await screen.findByText('Vendela');
    await user.click(screen.getByRole('button', { name: /new variety/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/variety name/i), 'Mondial');
    await user.type(within(dialog).getByLabelText(/^color/i), 'White');
    const submit = within(dialog).getByRole('button', { name: /create variety/i });
    act(() => { submit.click(); submit.click(); });              // same task
    act(() => { dialog.querySelector('form').requestSubmit(); }); // Enter while pending
    await waitFor(() => expect(posts(fetch, '/varieties')).toHaveLength(1));
    expect(submit).toBeDisabled();
    await act(async () => { release(); });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(fetch, '/varieties')).toHaveLength(1);
  });

  it('blocks a duplicate it can see, without calling the API', async () => {
    const user = userEvent.setup();
    const fetch = base();
    renderApp('/varieties');
    await screen.findByText('Vendela');
    await user.click(screen.getByRole('button', { name: /new variety/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/variety name/i), '  VENDELA ');
    await user.type(within(dialog).getByLabelText(/^color/i), 'Pink');
    await user.click(within(dialog).getByRole('button', { name: /create variety/i }));
    expect(within(dialog).getByText('A rose variety with this name already exists.')).toBeInTheDocument();
    expect(posts(fetch, '/varieties')).toHaveLength(0);
  });

  it('shows the API 409, keeps the typed values and lets the user retry', async () => {
    const user = userEvent.setup();
    const fetch = base({
      'POST /lots': reply(409, {
        error: "This lot already exists in the selected farm: 'Lot B' (lot #7)",
        code: 'DUPLICATE_RECORD',
        details: { name: 'A lot with this name already exists in the selected farm' },
      }),
    });
    renderApp('/lots');
    await screen.findByText('Lot A', { selector: 'td' });
    await user.click(screen.getByRole('button', { name: /new lot/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/lot name/i), 'Lot B');
    await user.type(within(dialog).getByLabelText(/^area/i), '2.5');
    await user.click(within(dialog).getByRole('button', { name: /create lot/i }));
    expect(await within(dialog).findByText(/This lot already exists in the selected farm: 'Lot B'/)).toBeInTheDocument();
    expect(within(dialog).getAllByText('A lot with this name already exists in the selected farm').length).toBeGreaterThan(0);
    expect(within(dialog).getByLabelText(/lot name/i)).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByLabelText(/lot name/i)).toHaveValue('Lot B');
    expect(within(dialog).getByLabelText(/^area/i)).toHaveValue(2.5);
    expect(within(dialog).getByRole('button', { name: /create lot/i })).toBeEnabled();
    expect(screen.queryByText('Lot created successfully')).not.toBeInTheDocument();
    expect(posts(fetch, '/lots')).toHaveLength(1);
  });

  it('allows saving an existing record without changing its identifying values', async () => {
    const user = userEvent.setup();
    const fetch = base({
      'PUT /varieties/1': ({ body }) => ({ variety: { variety_id: 1, ...body, crop_count: 1 } }),
    });
    renderApp('/varieties');
    await screen.findByText('Vendela');
    await user.click(screen.getByRole('button', { name: 'Edit Freedom' }));
    const dialog = screen.getByRole('dialog');
    const color = within(dialog).getByLabelText(/^color/i);
    await user.clear(color);
    await user.type(color, 'Dark red');
    await user.click(within(dialog).getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(fetch.calls.some((c) => c.method === 'PUT' && c.path === '/varieties/1')).toBe(true));
  });

  it('forecast wizard: an existing forecast for that crop and date cannot be saved again', async () => {
    const user = userEvent.setup();
    const calculation = {
      estimated_quantity: 1433.33, method: 'Moving Average (3 records)', window: 3,
      formula: '(1600 + 1500 + 1200) / 3 = 1433.33', history: [], saved: false, existing_forecast_id: 12,
    };
    const fetch = base({ 'POST /forecasts/generate': { calculation } });
    renderApp('/forecasts');
    await user.click(await screen.findByRole('button', { name: /generate forecast/i }));
    const dialog = screen.getByRole('dialog', { name: 'Generate forecast' });
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/forecast date/i), '2026-02-10');
    await user.click(within(dialog).getByRole('button', { name: /calculate estimate/i }));
    expect(await within(dialog).findByText(/This forecast already exists for the selected crop and date \(forecast #12\)/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /save forecast/i })).toBeDisabled();
    expect(fetch.calls.filter((c) => c.path === '/forecasts/generate')).toHaveLength(1);
  });
});
