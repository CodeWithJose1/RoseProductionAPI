import { api } from './client.js';

// One descriptor per REST resource. `listKey`/`itemKey` match the JSON keys
// returned by the Flask API.
function resource(path, listKey, itemKey, idKey) {
  return {
    path,
    idKey,
    list: (params) => api.get(path, params).then((data) => data[listKey] ?? []),
    get: (id) => api.get(`${path}/${id}`).then((data) => data[itemKey]),
    create: (body) => api.post(path, body).then((data) => data[itemKey]),
    update: (id, body) => api.put(`${path}/${id}`, body).then((data) => data[itemKey]),
    remove: (id) => api.delete(`${path}/${id}`),
  };
}

export const farmsApi = resource('/farms', 'farms', 'farm', 'farm_id');
export const lotsApi = resource('/lots', 'lots', 'lot', 'lot_id');
export const varietiesApi = resource('/varieties', 'varieties', 'variety', 'variety_id');
export const cropsApi = resource('/crops', 'crops', 'crop', 'crop_id');
export const seasonsApi = resource('/seasons', 'seasons', 'season', 'season_id');
export const harvestsApi = resource('/harvests', 'harvests', 'harvest', 'harvest_id');
export const forecastsApi = {
  ...resource('/forecasts', 'forecasts', 'forecast', 'forecast_id'),
  generate: (body) => api.post('/forecasts/generate', body),
  status: () => api.get('/forecasts/status').then((data) => data.rows ?? []),
  summary: () => api.get('/forecasts/summary').then((data) => data.rows ?? []),
};

export const statsApi = {
  dashboard: () => api.get('/stats/dashboard'),
  production: (params) => api.get('/stats/production', params),
};

export const authApi = {
  status: () => api.get('/auth/status'),
  login: (apiKey) => api.post('/auth/login', { api_key: apiKey }),
  logout: () => api.post('/auth/logout'),
};
