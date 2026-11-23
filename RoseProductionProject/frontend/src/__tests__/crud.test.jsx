import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockFetch, reply } from '../test/mockFetch.js';
import { renderApp } from '../test/renderApp.jsx';
import * as fx from '../test/fixtures.js';

function base(extra = {}) {
  return mockFetch({
    '/auth/status': { authenticated: true, auth_configured: true },
    '/farms': { count: 1, farms: fx.farms },
    '/lots': { count: 1, lots: fx.lots },
    '/crops': { count: 1, crops: fx.crops },
    '/seasons': { count: 1, seasons: fx.seasons },
    '/harvests': { count: 1, harvests: fx.harvests },
    ...extra,
  });
}

describe('rose variety CRUD', () => {
  it('creates, edits and deletes a variety through the API', async () => {
    const user = userEvent.setup();
    let list = [...fx.varieties];
    const fetch = base({
      '/varieties': () => ({ count: list.length, varieties: list }),
      'POST /varieties': ({ body }) => {
        const variety = { variety_id: 50, ...body, crop_count: 0 };
        list = [...list, variety];
        return reply(201, { variety });
      },
      'PUT /varieties/50': ({ body }) => {
        list = list.map((v) => (v.variety_id === 50 ? { ...v, ...body } : v));
        return { variety: list.find((v) => v.variety_id === 50) };
      },
      'DELETE /varieties/50': () => {
        list = list.filter((v) => v.variety_id !== 50);
        return { message: 'Rose variety deleted successfully' };
      },
    });
    renderApp('/varieties');
    await screen.findByText('Vendela');

    await user.click(screen.getByRole('button', { name: /new variety/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/variety name/i), 'GUI_TEST_Variety');
    await user.type(within(dialog).getByLabelText(/^color/i), 'Purple');
    await user.click(within(dialog).getByRole('button', { name: /create variety/i }));
    expect(await screen.findByText('GUI_TEST_Variety')).toBeInTheDocument();
    expect(screen.getByText('Variety created successfully')).toBeInTheDocument();
    const post = fetch.calls.find((c) => c.method === 'POST' && c.path === '/varieties');
    expect(JSON.parse(post.options.body)).toEqual({ name: 'GUI_TEST_Variety', color: 'Purple' });

    await user.click(screen.getByRole('button', { name: 'Edit GUI_TEST_Variety' }));
    const editDialog = screen.getByRole('dialog');
    const name = within(editDialog).getByLabelText(/variety name/i);
    await user.clear(name);
    await user.type(name, 'GUI_TEST_Updated');
    await user.click(within(editDialog).getByRole('button', { name: /save changes/i }));
    expect(await screen.findByText('GUI_TEST_Updated')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete GUI_TEST_Updated' }));
    const confirm = screen.getByRole('dialog', { name: /delete variety/i });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(screen.queryByText('GUI_TEST_Updated')).not.toBeInTheDocument());
  });

  it('keeps the dialog open and shows the reason when a delete is refused (409)', async () => {
    const user = userEvent.setup();
    base({
      '/varieties': { count: 2, varieties: fx.varieties },
      'DELETE /varieties/1': reply(409, { error: 'Cannot delete this rose variety: it is still referenced by 1 crop(s).', code: 'RECORD_IN_USE' }),
    });
    renderApp('/varieties');
    await user.click(await screen.findByRole('button', { name: 'Delete Freedom' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText(/still referenced by 1 crop/)).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('harvest form', () => {
  async function openForm(user) {
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.click(screen.getByRole('button', { name: /new harvest/i }));
    return screen.getByRole('dialog');
  }

  it('explains out-of-season dates and non-positive quantities', async () => {
    const user = userEvent.setup();
    const fetch = base({ '/varieties': { count: 2, varieties: fx.varieties } });
    const dialog = await openForm(user);
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/harvest date/i), '2026-03-01');
    await user.type(within(dialog).getByLabelText(/quantity/i), '0');
    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(within(dialog).getByText(/must be inside Valentines Day 2026 \(2026-02-01 to 2026-02-14\)/)).toBeInTheDocument();
    expect(within(dialog).getByText('Quantity must be greater than zero')).toBeInTheDocument();
    expect(fetch.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('posts a valid harvest and shows server-side rule violations', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    const fetch = base({
      '/varieties': { count: 2, varieties: fx.varieties },
      'POST /harvests': () => {
        attempt += 1;
        return attempt === 1
          ? reply(400, { error: 'Harvest date must be within the selected season', code: 'DATABASE_RULE_VIOLATION' })
          : reply(201, { harvest: { ...fx.harvests[0], harvest_id: 2 } });
      },
    });
    const dialog = await openForm(user);
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/harvest date/i), '2026-02-10');
    await user.type(within(dialog).getByLabelText(/quantity/i), '1500');
    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(await within(dialog).findByText('Harvest date must be within the selected season')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(await screen.findByText('Harvest created successfully')).toBeInTheDocument();
    const post = fetch.calls.filter((c) => c.method === 'POST' && c.path === '/harvests').at(-1);
    expect(JSON.parse(post.options.body)).toEqual({ crop_id: 1, season_id: 1, harvest_date: '2026-02-10', quantity: 1500 });
  });

  it('sends filter values as query parameters', async () => {
    const user = userEvent.setup();
    const fetch = base({ '/varieties': { count: 2, varieties: fx.varieties } });
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.selectOptions(screen.getByLabelText('Variety'), '1');
    await waitFor(() => expect(fetch.calls.some((c) => c.url.includes('/harvests?') && c.url.includes('variety_id=1'))).toBe(true));
  });
});

describe('harvest consistency rules (final audit)', () => {
  it('rejects dates before planting and in the future before calling the API', async () => {
    const user = userEvent.setup();
    const futureSeason = {
      season_id: 2, name: 'Season 2099', start_date: '2099-01-01', end_date: '2099-12-31',
      duration_days: 365, harvest_count: 0, forecast_count: 0,
    };
    const earlySeason = {
      season_id: 3, name: 'Season 2023', start_date: '2023-01-01', end_date: '2023-12-31',
      duration_days: 365, harvest_count: 0, forecast_count: 0,
    };
    const fetch = mockFetch({
      '/auth/status': { authenticated: true, auth_configured: true },
      '/lots': { count: 1, lots: fx.lots },
      '/varieties': { count: 2, varieties: fx.varieties },
      '/crops': { count: 1, crops: fx.crops },
      '/seasons': { count: 3, seasons: [...fx.seasons, futureSeason, earlySeason] },
      '/harvests': { count: 1, harvests: fx.harvests },
    });
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.click(screen.getByRole('button', { name: /new harvest/i }));
    const dialog = screen.getByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '2');
    await user.type(within(dialog).getByLabelText(/harvest date/i), '2099-03-01');
    await user.type(within(dialog).getByLabelText(/quantity/i), '10');
    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(within(dialog).getByText(/cannot be dated in the future/)).toBeInTheDocument();

    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '3');
    const dateInput = within(dialog).getByLabelText(/harvest date/i);
    await user.clear(dateInput);
    await user.type(dateInput, '2023-06-01');
    expect(within(dialog).getByText("The date must be on or after the crop's planting date (2024-03-01)")).toBeInTheDocument();
    expect(fetch.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('shows the duplicate-day conflict returned by the API (409)', async () => {
    // A duplicate the page cannot see (e.g. registered by someone else after
    // the list was loaded): the API refuses it and the form shows why.
    const user = userEvent.setup();
    base({
      '/varieties': { count: 2, varieties: fx.varieties },
      'POST /harvests': reply(409, {
        error: 'Crop #1 already has a harvest record on 2026-02-03 (harvest #9); edit that record instead',
        code: 'DUPLICATE_RECORD', details: { harvest_date: 'This crop already has a harvest on this date' },
      }),
    });
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.click(screen.getByRole('button', { name: /new harvest/i }));
    const dialog = screen.getByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/harvest date/i), '2026-02-03');
    await user.type(within(dialog).getByLabelText(/quantity/i), '10');
    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(await within(dialog).findByText(/already has a harvest record on 2026-02-03/)).toBeInTheDocument();
    expect(within(dialog).getAllByText('This crop already has a harvest on this date').length).toBeGreaterThan(0);
    expect(within(dialog).getByLabelText(/harvest date/i)).toHaveAttribute('aria-invalid', 'true');
  });

  it('flags a duplicate day it can already see without calling the API', async () => {
    const user = userEvent.setup();
    const fetch = base({ '/varieties': { count: 2, varieties: fx.varieties } });
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.click(screen.getByRole('button', { name: /new harvest/i }));
    const dialog = screen.getByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/harvest date/i), '2026-02-02');
    await user.type(within(dialog).getByLabelText(/quantity/i), '10');
    await user.click(within(dialog).getByRole('button', { name: /create harvest/i }));
    expect(within(dialog).getByText('This crop already has a harvest on this date. Edit that record instead.')).toBeInTheDocument();
    expect(fetch.calls.some((c) => c.method === 'POST')).toBe(false);
  });
});

describe('empty state with active filters (final audit)', () => {
  it('says that no record matches instead of "no records yet"', async () => {
    const user = userEvent.setup();
    base({
      '/varieties': { count: 2, varieties: fx.varieties },
      '/harvests': ({ url }) => (url.includes('?') ? { count: 0, harvests: [] } : { count: 1, harvests: fx.harvests }),
    });
    renderApp('/harvests');
    await screen.findByText('Valentines Day 2026', { selector: 'td' });
    await user.selectOptions(screen.getByLabelText('Variety'), '2');
    expect(await screen.findByText('No matching records')).toBeInTheDocument();
    expect(screen.getByText(/No records match the selected filters/)).toBeInTheDocument();
  });
});

describe('season form', () => {
  it('rejects an end date before the start date', async () => {
    const user = userEvent.setup();
    const fetch = base({ '/varieties': { count: 2, varieties: fx.varieties } });
    renderApp('/seasons');
    await screen.findByText('Valentines Day 2026');
    await user.click(screen.getByRole('button', { name: /new season/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/season name/i), 'Mothers Day 2027');
    await user.type(within(dialog).getByLabelText(/start date/i), '2027-05-10');
    await user.type(within(dialog).getByLabelText(/end date/i), '2027-05-01');
    await user.click(within(dialog).getByRole('button', { name: /create season/i }));
    expect(within(dialog).getByText('End date must be on or after the start date')).toBeInTheDocument();
    expect(fetch.calls.some((c) => c.method === 'POST')).toBe(false);
  });
});

describe('forecast generation', () => {
  it('previews the moving average and saves it', async () => {
    const user = userEvent.setup();
    const calculation = {
      estimated_quantity: 1433.33, window: 3, method: 'Moving Average (3 records)',
      formula: '(1600 + 1500 + 1200) / 3 = 1433.33',
      history: [
        { harvest_id: 3, harvest_date: '2026-02-08', quantity: 1600, season: 'Valentines Day 2026' },
        { harvest_id: 2, harvest_date: '2026-02-06', quantity: 1500, season: 'Valentines Day 2026' },
        { harvest_id: 1, harvest_date: '2026-02-04', quantity: 1200, season: 'Valentines Day 2026' },
      ],
      saved: false,
    };
    const fetch = base({
      '/varieties': { count: 2, varieties: fx.varieties },
      '/forecasts': { count: 0, forecasts: [] },
      '/forecasts/summary': { rows: [] },
      'POST /forecasts/generate': ({ body }) => (body.save
        ? reply(201, { calculation: { ...calculation, saved: true }, forecast: { forecast_id: 77, estimated_quantity: 1433.33 } })
        : { calculation }),
    });
    renderApp('/forecasts');
    await user.click(await screen.findByRole('button', { name: /generate forecast/i }));
    const dialog = screen.getByRole('dialog', { name: 'Generate forecast' });
    expect(within(dialog).getByRole('button', { name: /save forecast/i })).toBeDisabled();
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/forecast date/i), '2026-02-10');
    await user.click(within(dialog).getByRole('button', { name: /calculate estimate/i }));
    expect(await within(dialog).findByText('1,433.33 stems')).toBeInTheDocument();
    expect(within(dialog).getByText('(1600 + 1500 + 1200) / 3 = 1433.33')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: /save forecast/i }));
    expect(await within(dialog).findByText('Saved as forecast #77')).toBeInTheDocument();
    const calls = fetch.calls.filter((c) => c.path === '/forecasts/generate').map((c) => JSON.parse(c.options.body));
    expect(calls).toEqual([
      { crop_id: 1, season_id: 1, forecast_date: '2026-02-10', window: 3, save: false },
      { crop_id: 1, season_id: 1, forecast_date: '2026-02-10', window: 3, save: true },
    ]);
  });

  it('shows the insufficient-history error from the API', async () => {
    const user = userEvent.setup();
    base({
      '/varieties': { count: 2, varieties: fx.varieties },
      '/forecasts': { count: 0, forecasts: [] },
      '/forecasts/summary': { rows: [] },
      'POST /forecasts/generate': reply(400, { error: 'Not enough history: the moving average needs 3 harvest record(s)', code: 'INSUFFICIENT_HISTORY' }),
    });
    renderApp('/forecasts');
    await user.click(await screen.findByRole('button', { name: /generate forecast/i }));
    const dialog = screen.getByRole('dialog', { name: 'Generate forecast' });
    await user.selectOptions(within(dialog).getByLabelText(/^crop/i), '1');
    await user.selectOptions(within(dialog).getByLabelText(/^season/i), '1');
    await user.type(within(dialog).getByLabelText(/forecast date/i), '2026-02-02');
    await user.click(within(dialog).getByRole('button', { name: /calculate estimate/i }));
    expect(await within(dialog).findByText(/Not enough history/)).toBeInTheDocument();
  });
});
