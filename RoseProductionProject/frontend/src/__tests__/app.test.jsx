import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockFetch, reply } from '../test/mockFetch.js';
import { renderApp } from '../test/renderApp.jsx';
import * as fx from '../test/fixtures.js';

const signedIn = { authenticated: true, auth_configured: true };

function api(extra = {}) {
  return mockFetch({
    '/auth/status': signedIn,
    '/stats/dashboard': fx.dashboard,
    '/farms': { count: 1, farms: fx.farms },
    '/lots': { count: 1, lots: fx.lots },
    '/varieties': { count: 2, varieties: fx.varieties },
    '/crops': { count: 1, crops: fx.crops },
    '/seasons': { count: 1, seasons: fx.seasons },
    '/harvests': { count: 1, harvests: fx.harvests },
    '/forecasts': { count: 0, forecasts: [] },
    '/forecasts/summary': { rows: [] },
    '/stats/production': { group_by: 'variety', overall: fx.dashboard.production, groups: fx.dashboard.by_variety },
    ...extra,
  });
}

describe('authentication', () => {
  it('shows the login screen when not signed in and signs in', async () => {
    const user = userEvent.setup();
    let authenticated = false;
    const fetch = api({
      '/auth/status': () => ({ authenticated, auth_configured: true }),
      'POST /auth/login': ({ body }) => {
        if (body.api_key !== 'right') return reply(401, { error: 'Invalid access key' });
        authenticated = true;
        return { authenticated: true };
      },
    });
    renderApp();
    const input = await screen.findByLabelText('Access key');

    await user.type(input, 'wrong');
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByText('Invalid access key')).toBeInTheDocument();
    expect(input).toHaveValue(''); // the key is not kept in the form

    await user.type(input, 'right');
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();

    const loginCall = fetch.calls.find((c) => c.path === '/auth/login' && c.body !== null);
    expect(loginCall).toBeTruthy();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it('requires an access key before calling the API', async () => {
    const user = userEvent.setup();
    const fetch = api({ '/auth/status': { authenticated: false, auth_configured: true } });
    renderApp();
    await user.click(await screen.findByRole('button', { name: /sign in/i }));
    expect(screen.getByText('Enter the access key to continue.')).toBeInTheDocument();
    expect(fetch.calls.some((c) => c.path === '/auth/login')).toBe(false);
  });

  it('returns to the login screen when the session expires (401)', async () => {
    api({ '/stats/dashboard': reply(401, { error: 'Unauthorized' }) });
    renderApp();
    expect(await screen.findByLabelText('Access key')).toBeInTheDocument();
    expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
  });

  it('shows a connection error when the API is down', async () => {
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
    renderApp();
    expect(await screen.findByText('Cannot reach the API')).toBeInTheDocument();
  });

  it('signs out', async () => {
    const user = userEvent.setup();
    api({ 'POST /auth/logout': { authenticated: false } });
    renderApp();
    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(screen.getByRole('button', { name: /sign out/i }));
    expect(await screen.findByLabelText('Access key')).toBeInTheDocument();
  });
});

describe('navigation and dashboard', () => {
  it('renders real API figures on the dashboard', async () => {
    api();
    renderApp();
    await screen.findByRole('heading', { name: 'Dashboard' });
    const total = screen.getByText('Total stems').closest('article');
    expect(within(total).getByText('1,200')).toBeInTheDocument();
    expect(screen.getByText('Production by rose variety')).toBeInTheDocument();
    expect(screen.getByText('No upcoming seasons')).toBeInTheDocument();
  });

  it('shows empty states when the database has no production', async () => {
    api({ '/stats/dashboard': fx.emptyDashboard });
    renderApp();
    await screen.findByRole('heading', { name: 'Dashboard' });
    expect(screen.getAllByText('No data available').length).toBeGreaterThanOrEqual(3);
  });

  it('shows an error state with retry when the dashboard fails', async () => {
    const user = userEvent.setup();
    let fail = true;
    api({ '/stats/dashboard': () => (fail ? reply(503, { error: 'The database is not available' }) : fx.dashboard) });
    renderApp();
    expect(await screen.findByText('The database is not available')).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it.each([
    ['Farms', 'Farm One'],
    ['Lots', 'Lot A'],
    ['Rose varieties', 'Vendela'],
    ['Crops', 'Freedom'],
    ['Seasons', 'Valentines Day 2026'],
    ['Harvests', '1,200'],
    ['Forecasts', 'No forecasts yet'],
    ['Production analysis', 'Statistics by rose variety'],
  ])('navigates to %s from the sidebar', async (label, expected) => {
    const user = userEvent.setup();
    api();
    renderApp();
    await screen.findByRole('heading', { name: 'Dashboard' });
    const nav = screen.getByRole('complementary', { name: 'Main navigation' });
    await user.click(within(nav).getByRole('link', { name: label }));
    expect(await screen.findByRole('heading', { level: 1, name: label })).toBeInTheDocument();
    expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0);
  });

  it('opens and closes the mobile menu', async () => {
    const user = userEvent.setup();
    api();
    const { container } = renderApp();
    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(container.querySelector('.app-shell')).toHaveClass('nav-open');
    await user.click(screen.getByRole('button', { name: 'Close menu' }));
    expect(container.querySelector('.app-shell')).not.toHaveClass('nav-open');
  });
});
