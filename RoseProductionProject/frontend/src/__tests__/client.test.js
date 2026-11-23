import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, buildQuery, onUnauthorized } from '../api/client.js';
import { mockFetch, reply } from '../test/mockFetch.js';

afterEach(() => vi.restoreAllMocks());

describe('api client', () => {
  it('sends same-origin credentials and no API key', async () => {
    const fetch = mockFetch({ '/farms': { count: 0, farms: [] } });
    await api.get('/farms');
    const [, options] = fetch.mock.calls[0];
    expect(options.credentials).toBe('same-origin');
    expect(Object.keys(options.headers)).not.toContain('X-API-Key');
  });

  it('adds the GUI (CSRF) header and JSON body on writes', async () => {
    const fetch = mockFetch({ 'POST /varieties': reply(201, { variety: { variety_id: 9 } }) });
    await api.post('/varieties', { name: 'A', color: 'Red' });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers['X-Requested-With']).toBe('RoseProductionGUI');
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(options.body)).toEqual({ name: 'A', color: 'Red' });
  });

  it('turns error JSON into ApiError with status, code and details', async () => {
    mockFetch({
      'POST /harvests': reply(400, { error: 'Validation failed', code: 'VALIDATION_ERROR', details: { quantity: 'must be greater than zero' } }),
    });
    const error = await api.post('/harvests', {}).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(400);
    expect(error.code).toBe('VALIDATION_ERROR');
    expect(error.details.quantity).toMatch(/greater than zero/);
  });

  it.each([
    [403, /not allowed/i], [404, /not found/i], [409, /conflict/i], [500, /server failed/i], [503, /unavailable/i],
  ])('uses a readable default message for HTTP %s without JSON body', async (status, pattern) => {
    globalThis.fetch = vi.fn(async () => new Response('oops', { status, headers: { 'Content-Type': 'text/plain' } }));
    const error = await api.get(`/x${status}`).catch((e) => e);
    expect(error.status).toBe(status);
    expect(error.message).toMatch(pattern);
  });

  it('notifies listeners on 401 for API calls', async () => {
    mockFetch({ '/farms': reply(401, { error: 'Unauthorized' }) });
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    await api.get('/farms').catch(() => {});
    unsubscribe();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('does not treat a failed login as an expired session', async () => {
    mockFetch({ 'POST /auth/login': reply(401, { error: 'Invalid access key' }) });
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    const error = await api.post('/auth/login', { api_key: 'x' }).catch((e) => e);
    unsubscribe();
    expect(error.message).toBe('Invalid access key');
    expect(listener).not.toHaveBeenCalled();
  });

  it('reports network failures with status 0', async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
    const error = await api.get('/farms').catch((e) => e);
    expect(error.status).toBe(0);
    expect(error.message).toMatch(/cannot reach/i);
  });

  it('de-duplicates identical concurrent GET requests', async () => {
    const fetch = mockFetch({ '/seasons': { count: 0, seasons: [] } });
    await Promise.all([api.get('/seasons'), api.get('/seasons'), api.get('/seasons')]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('builds query strings without empty values', () => {
    expect(buildQuery({ crop_id: 3, season_id: '', date_from: null })).toBe('?crop_id=3');
    expect(buildQuery({})).toBe('');
  });
});
