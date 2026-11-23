import { useState } from 'react';
import { Sprout } from 'lucide-react';
import { cropsApi } from '../api/endpoints.js';
import { ColorSwatch, FilterBar, FilterSelect } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { SelectInput, TextInput } from '../components/FormField.jsx';
import { ErrorState } from '../components/States.jsx';
import { toOptions, useLookups } from '../hooks/useLookups.js';
import { formatDate, formatInt } from '../utils/format.js';
import {
  findClash, rules, runRules, withDuplicate,
} from '../utils/validation.js';

const schema = {
  lot_id: [rules.required('Lot')],
  variety_id: [rules.required('Rose variety')],
  planting_date: [rules.required('Planting date'), rules.date('Planting date')],
};

// The same variety may be planted again in a lot (new crop cycle), but not
// twice on the same date.
export function validateCrop(values, { rows, editing } = {}) {
  const sameKey = (lotId, varietyId, date) => String(lotId) === String(values.lot_id)
    && String(varietyId) === String(values.variety_id) && date === values.planting_date;
  const clash = findClash({
    rows,
    idKey: 'crop_id',
    editing,
    unchanged: editing && sameKey(editing.lot.lot_id, editing.variety.variety_id, editing.planting_date),
    sameAs: (row) => sameKey(row.lot.lot_id, row.variety.variety_id, row.planting_date),
  });
  return withDuplicate(runRules(values, schema), 'planting_date', clash,
    'This variety is already planted in this lot on this date.');
}

export default function Crops() {
  const lookups = useLookups(['lots', 'varieties']);
  const [filters, setFilters] = useState({ lot_id: '', variety_id: '' });
  const lotOptions = toOptions.lots(lookups.data?.lots);
  const varietyOptions = toOptions.varieties(lookups.data?.varieties);
  const setFilter = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));

  const columns = [
    { key: 'crop_id', header: 'ID', align: 'right' },
    { key: 'variety', header: 'Variety', render: (row) => row.variety.name, sortValue: (row) => row.variety.name },
    { key: 'color', header: 'Color', render: (row) => <ColorSwatch color={row.variety.color} />, sortValue: (row) => row.variety.color },
    { key: 'lot', header: 'Lot', render: (row) => row.lot.name, sortValue: (row) => row.lot.name },
    { key: 'planting_date', header: 'Planting date', render: (row) => formatDate(row.planting_date) },
    { key: 'harvest_count', header: 'Harvests', align: 'right', render: (row) => formatInt(row.harvest_count) },
    { key: 'forecast_count', header: 'Forecasts', align: 'right', render: (row) => formatInt(row.forecast_count) },
  ];

  return (
    <CrudPage
      api={cropsApi}
      title="Crops"
      singular="Crop"
      icon={Sprout}
      description="Each crop is one rose variety planted in one lot."
      params={filters}
      beforeTable={lookups.error ? <ErrorState error={lookups.error} onRetry={lookups.reload} title="Could not load lots/varieties" /> : null}
      filters={(
        <FilterBar onReset={() => setFilters({ lot_id: '', variety_id: '' })} active={Boolean(filters.lot_id || filters.variety_id)}>
          <FilterSelect label="Lot" value={filters.lot_id} onChange={setFilter('lot_id')} options={lotOptions} allLabel="All lots" />
          <FilterSelect label="Variety" value={filters.variety_id} onChange={setFilter('variety_id')} options={varietyOptions} allLabel="All varieties" />
        </FilterBar>
      )}
      filtersActive={Boolean(filters.lot_id || filters.variety_id)}
      columns={columns}
      searchText={(row) => `${row.crop_id} ${row.variety.name} ${row.variety.color} ${row.lot.name} ${row.planting_date}`}
      emptyForm={{ lot_id: '', variety_id: '', planting_date: '' }}
      toForm={(row) => ({ lot_id: String(row.lot.lot_id), variety_id: String(row.variety.variety_id), planting_date: row.planting_date })}
      toPayload={(values) => ({
        lot_id: Number(values.lot_id), variety_id: Number(values.variety_id), planting_date: values.planting_date,
      })}
      validate={validateCrop}
      describe={(row) => `Crop #${row.crop_id} · ${row.variety.name} in ${row.lot.name}`}
      renderFields={({ values, set, errors }) => (
        <>
          <SelectInput label="Lot" required value={values.lot_id} onChange={(v) => set('lot_id', v)} options={lotOptions} error={errors.lot_id} placeholder={lookups.loading ? 'Loading lots…' : 'Select a lot'} />
          <SelectInput label="Rose variety" required value={values.variety_id} onChange={(v) => set('variety_id', v)} options={varietyOptions} error={errors.variety_id} placeholder={lookups.loading ? 'Loading varieties…' : 'Select a variety'} />
          <TextInput label="Planting date" required type="date" value={values.planting_date} onChange={(v) => set('planting_date', v)} error={errors.planting_date} />
        </>
      )}
    />
  );
}
