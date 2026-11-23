import { vi } from 'vitest';

/**
 * Minimal fetch mock for component tests. `routes` maps "METHOD /path" (or
 * "/path" for GET) to a handler returning { status, body } or a body.
 */
export function mockFetch(routes) {
  const calls = [];
  const fn = vi.fn(async (url, options = {}) => {
    const method = (options.method || 'GET').toUpperCase();
    const path = String(url).split('?')[0];
    calls.push({ method, url: String(url), path, options });
    const handler = routes[`${method} ${path}`] ?? (method === 'GET' ? routes[path] : undefined);
    if (!handler) {
      return new Response(JSON.stringify({ error: `No mock for ${method} ${path}` }), {
        status: 500, headers: { 'Content-Type': 'application/json' },
      });
    }
    const result = typeof handler === 'function'
      ? await handler({ method, url: String(url), options, body: options.body ? JSON.parse(options.body) : undefined })
      : handler;
    const status = result && result.__status ? result.__status : 200;
    const body = result && result.__status ? result.body : result;
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  });
  fn.calls = calls;
  globalThis.fetch = fn;
  return fn;
}

export const reply = (status, body) => ({ __status: status, body });
