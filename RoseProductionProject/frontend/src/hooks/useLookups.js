import { useApi } from './useApi.js';
import {
  cropsApi, farmsApi, lotsApi, seasonsApi, varietiesApi,
} from '../api/endpoints.js';

const LOADERS = {
  farms: () => farmsApi.list(),
  lots: () => lotsApi.list(),
  varieties: () => varietiesApi.list(),
  crops: () => cropsApi.list(),
  seasons: () => seasonsApi.list(),
};

/**
 * Loads reference lists used by dropdowns/filters, from the real API.
 * Usage: const { data, loading, error, reload } = useLookups(['lots', 'varieties'])
 */
export function useLookups(names) {
  return useApi(async () => {
    const entries = await Promise.all(names.map(async (name) => [name, await LOADERS[name]()]));
    return Object.fromEntries(entries);
  }, [names.join(',')]);
}

export const toOptions = {
  farms: (rows = []) => rows.map((f) => ({ value: String(f.farm_id), label: `${f.name} — ${f.location}` })),
  lots: (rows = []) => rows.map((l) => ({ value: String(l.lot_id), label: `${l.name} (${l.farm.name})` })),
  varieties: (rows = []) => rows.map((v) => ({ value: String(v.variety_id), label: `${v.name} · ${v.color}` })),
  crops: (rows = []) => rows.map((c) => ({
    value: String(c.crop_id),
    label: `#${c.crop_id} · ${c.variety.name} · ${c.lot.name}`,
  })),
  seasons: (rows = []) => rows.map((s) => ({
    value: String(s.season_id),
    label: `${s.name} (${s.start_date} → ${s.end_date})`,
  })),
};
