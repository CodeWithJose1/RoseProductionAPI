import { useMemo, useState } from 'react';
import { Scissors } from 'lucide-react';
import { harvestsApi } from '../api/endpoints.js';
import { FilterBar, FilterDate, FilterSelect } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { SelectInput, TextInput } from '../components/FormField.jsx';
import { ErrorState } from '../components/States.jsx';
import { toOptions, useLookups } from '../hooks/useLookups.js';
import { formatDate, formatInt, todayIso } from '../utils/format.js';
import {
  dateWithin, findClash, rules, runRules, withDuplicate,
} from '../utils/validation.js';

const EMPTY_FILTERS = { date_from: '', date_to: '', variety_id: '', crop_id: '', season_id: '', lot_id: '' };

export default function Harvests() {
  const lookups = useLookups(['crops', 'seasons', 'varieties', 'lots']);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const setFilter = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  const filtersActive = Object.values(filters).some(Boolean);
  const dateRangeInvalid = filters.date_from && filters.date_to && filters.date_from > filters.date_to;

  const seasons = lookups.data?.seasons || [];
  const seasonById = useMemo(
    () => Object.fromEntries(seasons.map((s) => [String(s.season_id), s])),
    [seasons],
  );
  const crops = lookups.data?.crops || [];
  const cropById = useMemo(
    () => Object.fromEntries(crops.map((c) => [String(c.crop_id), c])),
    [crops],
  );
  const cropOptions = toOptions.crops(crops);
  const today = todayIso();
  const seasonOptions = toOptions.seasons(seasons);

  const schema = {
    crop_id: [rules.required('Crop')],
    season_id: [rules.required('Season')],
    harvest_date: [
      rules.required('Harvest date'),
      rules.date('Harvest date'),
      (value, values) => {
        const season = seasonById[values.season_id];
        if (season && value && !dateWithin(value, season.start_date, season.end_date)) {
          return `The date must be inside ${season.name} (${season.start_date} to ${season.end_date})`;
        }
        return null;
      },
      (value, values) => {
        const crop = cropById[values.crop_id];
        return crop && value && value < crop.planting_date
          ? `The date must be on or after the crop's planting date (${crop.planting_date})` : null;
      },
      (value) => (value && value > today ? `A harvest cannot be dated in the future (today is ${today})` : null),
    ],
    quantity: [rules.required('Quantity'), rules.positiveInteger('Quantity')],
  };

  const columns = [
    { key: 'harvest_id', header: 'ID', align: 'right' },
    { key: 'harvest_date', header: 'Date', render: (row) => formatDate(row.harvest_date) },
    { key: 'variety', header: 'Variety', render: (row) => row.crop.variety, sortValue: (row) => row.crop.variety },
    { key: 'lot', header: 'Lot', render: (row) => row.crop.lot, sortValue: (row) => row.crop.lot },
    { key: 'crop', header: 'Crop', render: (row) => `#${row.crop.crop_id}`, sortValue: (row) => row.crop.crop_id },
    { key: 'season', header: 'Season', render: (row) => row.season.name, sortValue: (row) => row.season.name },
    { key: 'quantity', header: 'Stems', align: 'right', render: (row) => formatInt(row.quantity) },
  ];

  const apiParams = dateRangeInvalid ? { ...filters, date_to: '' } : filters;

  return (
    <CrudPage
      api={harvestsApi}
      title="Harvests"
      singular="Harvest"
      icon={Scissors}
      description="Daily harvest records: crop, season, date and number of stems harvested."
      params={apiParams}
      initialSort={{ key: 'harvest_date', dir: 'desc' }}
      beforeTable={lookups.error ? <ErrorState error={lookups.error} onRetry={lookups.reload} title="Could not load reference data" /> : null}
      filters={(
        <>
          <FilterBar onReset={() => setFilters(EMPTY_FILTERS)} active={filtersActive}>
            <FilterDate label="From" value={filters.date_from} onChange={setFilter('date_from')} />
            <FilterDate label="To" value={filters.date_to} onChange={setFilter('date_to')} />
            <FilterSelect label="Variety" value={filters.variety_id} onChange={setFilter('variety_id')} options={toOptions.varieties(lookups.data?.varieties)} allLabel="All varieties" />
            <FilterSelect label="Lot" value={filters.lot_id} onChange={setFilter('lot_id')} options={toOptions.lots(lookups.data?.lots)} allLabel="All lots" />
            <FilterSelect label="Crop" value={filters.crop_id} onChange={setFilter('crop_id')} options={cropOptions} allLabel="All crops" />
            <FilterSelect label="Season" value={filters.season_id} onChange={setFilter('season_id')} options={seasonOptions} allLabel="All seasons" />
          </FilterBar>
          {dateRangeInvalid && <p className="field-error filter-error" role="alert">“From” must be on or before “To”; the end date is ignored.</p>}
        </>
      )}
      filtersActive={filtersActive}
      columns={columns}
      searchText={(row) => `${row.harvest_id} #${row.crop.crop_id} ${row.crop.variety} ${row.crop.lot} ${row.season.name} ${row.harvest_date} ${row.quantity}`}
      emptyForm={{ crop_id: '', season_id: '', harvest_date: '', quantity: '' }}
      toForm={(row) => ({
        crop_id: String(row.crop.crop_id), season_id: String(row.season.season_id),
        harvest_date: row.harvest_date, quantity: String(row.quantity),
      })}
      toPayload={(values) => ({
        crop_id: Number(values.crop_id), season_id: Number(values.season_id),
        harvest_date: values.harvest_date, quantity: Number(values.quantity),
      })}
      validate={(values, { rows, editing } = {}) => {
        // One record per crop and day (the API and the database enforce it).
        const sameKey = (cropId, date) => String(cropId) === String(values.crop_id) && date === values.harvest_date;
        const clash = findClash({
          rows,
          idKey: 'harvest_id',
          editing,
          unchanged: editing && sameKey(editing.crop.crop_id, editing.harvest_date),
          sameAs: (row) => sameKey(row.crop.crop_id, row.harvest_date),
        });
        return withDuplicate(runRules(values, schema), 'harvest_date', clash,
          'This crop already has a harvest on this date. Edit that record instead.');
      }}
      describe={(row) => `Harvest #${row.harvest_id} (${row.crop.variety}, ${row.harvest_date})`}
      formDescription="One record per crop and day. The date must fall inside the selected season, not before the crop was planted and not in the future; the quantity must be a positive whole number."
      renderFields={({ values, set, errors }) => {
        const season = seasonById[values.season_id];
        const crop = cropById[values.crop_id];
        const minDate = [season?.start_date, crop?.planting_date].filter(Boolean).sort().at(-1);
        const maxDate = [season?.end_date, today].filter(Boolean).sort()[0];
        return (
          <>
            <SelectInput label="Crop" required value={values.crop_id} onChange={(v) => set('crop_id', v)} options={cropOptions} error={errors.crop_id} placeholder={lookups.loading ? 'Loading crops…' : 'Select a crop'} />
            <SelectInput label="Season" required value={values.season_id} onChange={(v) => set('season_id', v)} options={seasonOptions} error={errors.season_id} placeholder={lookups.loading ? 'Loading seasons…' : 'Select a season'} />
            <div className="form-row">
              <TextInput
                label="Harvest date"
                required
                type="date"
                min={minDate}
                max={maxDate}
                value={values.harvest_date}
                onChange={(v) => set('harvest_date', v)}
                error={errors.harvest_date}
                hint={season ? `Allowed: ${minDate} to ${maxDate}` : 'Select a season first'}
              />
              <TextInput
                label="Quantity (stems)"
                required
                type="number"
                min="1"
                step="1"
                value={values.quantity}
                onChange={(v) => set('quantity', v)}
                error={errors.quantity}
                hint="Whole number greater than zero"
              />
            </div>
          </>
        );
      }}
    />
  );
}
