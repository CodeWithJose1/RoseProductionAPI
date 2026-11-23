import { useState } from 'react';
import { LayoutGrid } from 'lucide-react';
import { lotsApi } from '../api/endpoints.js';
import { FilterBar, FilterSelect } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { SelectInput, TextInput } from '../components/FormField.jsx';
import { ErrorState } from '../components/States.jsx';
import { toOptions, useLookups } from '../hooks/useLookups.js';
import { formatNumber } from '../utils/format.js';
import {
  findClash, normalizeText, rules, runRules, textKey, withDuplicate,
} from '../utils/validation.js';

const schema = {
  farm_id: [rules.required('Farm')],
  name: [rules.required('Lot name'), rules.maxLength('Lot name', 100)],
  area: [rules.required('Area'), rules.positiveNumber('Area', 99999999.99)],
};

// A lot name is unique inside its farm; case and spacing ignored.
export function validateLot(values, { rows, editing } = {}) {
  const sameKey = (farmId, name) => String(farmId) === String(values.farm_id)
    && textKey(name) === textKey(values.name);
  const clash = findClash({
    rows,
    idKey: 'lot_id',
    editing,
    unchanged: editing && sameKey(editing.farm.farm_id, editing.name),
    sameAs: (row) => sameKey(row.farm.farm_id, row.name),
  });
  return withDuplicate(runRules(values, schema), 'name', clash,
    'This lot already exists in the selected farm.');
}

export default function Lots() {
  const lookups = useLookups(['farms']);
  const [farmFilter, setFarmFilter] = useState('');
  const farmOptions = toOptions.farms(lookups.data?.farms);

  const columns = [
    { key: 'lot_id', header: 'ID', align: 'right' },
    { key: 'name', header: 'Lot' },
    { key: 'farm', header: 'Farm', render: (row) => row.farm.name, sortValue: (row) => row.farm.name },
    { key: 'area', header: 'Area', align: 'right', render: (row) => formatNumber(row.area) },
    { key: 'crop_count', header: 'Crops', align: 'right' },
  ];

  return (
    <CrudPage
      api={lotsApi}
      title="Lots"
      singular="Lot"
      icon={LayoutGrid}
      description="Cultivation lots and the farm each one belongs to."
      params={{ farm_id: farmFilter }}
      onChanged={lookups.reload}
      beforeTable={lookups.error ? <ErrorState error={lookups.error} onRetry={lookups.reload} title="Could not load farms" /> : null}
      filters={(
        <FilterBar onReset={() => setFarmFilter('')} active={Boolean(farmFilter)}>
          <FilterSelect label="Farm" value={farmFilter} onChange={setFarmFilter} options={farmOptions} allLabel="All farms" />
        </FilterBar>
      )}
      filtersActive={Boolean(farmFilter)}
      columns={columns}
      searchText={(row) => `${row.name} ${row.farm.name}`}
      emptyForm={{ farm_id: farmOptions.length === 1 ? farmOptions[0].value : '', name: '', area: '' }}
      toForm={(row) => ({ farm_id: String(row.farm.farm_id), name: row.name, area: String(row.area) })}
      toPayload={(values) => ({ farm_id: Number(values.farm_id), name: normalizeText(values.name), area: Number(values.area) })}
      validate={validateLot}
      describe={(row) => `${row.name} (${row.farm.name})`}
      renderFields={({ values, set, errors }) => (
        <>
          <SelectInput
            label="Farm"
            required
            value={values.farm_id}
            onChange={(v) => set('farm_id', v)}
            options={farmOptions}
            error={errors.farm_id}
            placeholder={lookups.loading ? 'Loading farms…' : 'Select a farm'}
          />
          <TextInput label="Lot name" required value={values.name} onChange={(v) => set('name', v)} error={errors.name} maxLength={100} />
          <TextInput
            label="Area"
            required
            type="number"
            min="0.01"
            step="0.01"
            value={values.area}
            onChange={(v) => set('area', v)}
            error={errors.area}
            hint="Cultivated area; must be greater than zero (up to 2 decimals)."
          />
        </>
      )}
    />
  );
}
