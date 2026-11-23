// Sample payloads shaped exactly like the Flask API responses (unit tests only).
export const farms = [{ farm_id: 1, name: 'Farm One', location: 'Cayambe', lot_count: 1 }];
export const lots = [{ lot_id: 1, name: 'Lot A', area: 1.5, farm: { farm_id: 1, name: 'Farm One' }, farm_id: 1, crop_count: 1 }];
export const varieties = [
  { variety_id: 1, name: 'Freedom', color: 'Red', crop_count: 1 },
  { variety_id: 2, name: 'Vendela', color: 'White', crop_count: 0 },
];
export const crops = [{
  crop_id: 1, planting_date: '2024-03-01', lot: { lot_id: 1, name: 'Lot A', farm_id: 1 },
  variety: { variety_id: 1, name: 'Freedom', color: 'Red' }, lot_id: 1, variety_id: 1,
  label: '#1 · Freedom · Lot A', harvest_count: 3, forecast_count: 0,
}];
export const seasons = [{
  season_id: 1, name: 'Valentines Day 2026', start_date: '2026-02-01', end_date: '2026-02-14',
  duration_days: 14, harvest_count: 3, forecast_count: 0,
}];
export const harvests = [{
  harvest_id: 1, harvest_date: '2026-02-02', quantity: 1200,
  crop: { crop_id: 1, variety: 'Freedom', lot: 'Lot A', variety_id: 1, lot_id: 1, color: 'Red' },
  season: { season_id: 1, name: 'Valentines Day 2026' }, crop_id: 1, season_id: 1,
}];
export const dashboard = {
  today: '2026-11-22',
  counts: { farms: 1, lots: 1, varieties: 2, crops: 1, seasons: 1, harvests: 1, forecasts: 0 },
  total_area: 1.5,
  production: { total: 1200, average: 1200, minimum: 1200, maximum: 1200, records: 1 },
  by_variety: [{ key: 1, label: 'Freedom', total: 1200, average: 1200, minimum: 1200, maximum: 1200, records: 1, color: 'Red' }],
  by_season: [{ key: 1, label: 'Valentines Day 2026', total: 1200, average: 1200, minimum: 1200, maximum: 1200, records: 1, start_date: '2026-02-01', end_date: '2026-02-14' }],
  over_time: [{ date: '2026-02-02', total: 1200, records: 1 }],
  upcoming_seasons: [],
  forecast_status: {},
  forecast_vs_actual: [],
};
export const emptyDashboard = {
  ...dashboard,
  counts: { farms: 0, lots: 0, varieties: 0, crops: 0, seasons: 0, harvests: 0, forecasts: 0 },
  total_area: 0,
  production: { total: 0, average: null, minimum: null, maximum: null, records: 0 },
  by_variety: [], by_season: [], over_time: [],
};
