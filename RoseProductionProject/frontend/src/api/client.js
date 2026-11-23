// Centralized HTTP client for the Flask API.
//
// * Same-origin requests only: the GUI is served by Flask (/app/) or by the
//   Vite dev server, which proxies API paths to Flask.
// * Authentication is the HttpOnly session cookie issued by /auth/login.
//   No API key is stored or embedded anywhere in the front-end.
// * Every state-changing request carries X-Requested-With, which the API
//   requires for cookie-authenticated writes (CSRF protection).

export const GUI_HEADER = 'X-Requested-With';
export const GUI_HEADER_VALUE = 'RoseProductionGUI';

export class ApiError extends Error {
  constructor(status, message, { details = null, code = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    this.code = code;
  }

  get isAuth() {
    return this.status === 401;
  }
}

const listeners = new Set();

/** Subscribe to 401 responses (session expired / not signed in). */
export function onUnauthorized(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function describeStatus(status) {
  if (status === 0) return 'Cannot reach the server. Check that the API is running.';
  if (status === 401) return 'Your session has expired. Please sign in again.';
  if (status === 403) return 'You are not allowed to perform this action.';
  if (status === 404) return 'The requested record was not found.';
  if (status === 409) return 'The operation conflicts with existing data.';
  if (status === 429) return 'Too many attempts. Please wait a few minutes.';
  if (status === 503) return 'The service or database is temporarily unavailable.';
  if (status >= 500) return 'The server failed to process the request.';
  return 'The request could not be completed.';
}

function buildQuery(params) {
  if (!params) return '';
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.append(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

// In-flight GET de-duplication: identical concurrent GETs share one request.
const inFlight = new Map();

async function send(method, path, { body, params, signal } = {}) {
  const url = `${path}${buildQuery(params)}`;
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers[GUI_HEADER] = GUI_HEADER_VALUE;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: 'same-origin',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError(0, describeStatus(0), { code: 'NETWORK_ERROR' });
  }

  let payload = null;
  const type = response.headers.get('content-type') || '';
  if (type.includes('application/json')) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const message = (payload && typeof payload.error === 'string' && payload.error)
      || describeStatus(response.status);
    const error = new ApiError(response.status, message, {
      details: payload?.details ?? null,
      code: payload?.code ?? null,
    });
    if (response.status === 401 && !path.startsWith('/auth/')) {
      listeners.forEach((listener) => listener(error));
    }
    throw error;
  }
  return payload;
}

export const api = {
  get(path, params) {
    const key = `${path}${buildQuery(params)}`;
    if (inFlight.has(key)) return inFlight.get(key);
    const promise = send('GET', path, { params }).finally(() => inFlight.delete(key));
    inFlight.set(key, promise);
    return promise;
  },
  post: (path, body) => send('POST', path, { body: body ?? {} }),
  put: (path, body) => send('PUT', path, { body }),
  delete: (path) => send('DELETE', path),
};

export { describeStatus, buildQuery };
