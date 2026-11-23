import { Flower2 } from 'lucide-react';
import { varietiesApi } from '../api/endpoints.js';
import { ColorSwatch } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { TextInput } from '../components/FormField.jsx';
import {
  findClash, normalizeText, rules, runRules, textKey, withDuplicate,
} from '../utils/validation.js';

const schema = {
  name: [rules.required('Variety name'), rules.maxLength('Variety name', 100)],
  color: [rules.required('Color'), rules.maxLength('Color', 50)],
};

// A variety is identified by its name (any colour); case and spacing ignored.
export function validateVariety(values, { rows, editing } = {}) {
  const clash = findClash({
    rows,
    idKey: 'variety_id',
    editing,
    unchanged: editing && textKey(editing.name) === textKey(values.name),
    sameAs: (row) => textKey(row.name) === textKey(values.name),
  });
  return withDuplicate(runRules(values, schema), 'name', clash,
    'A rose variety with this name already exists.');
}

export default function Varieties() {
  const columns = [
    { key: 'variety_id', header: 'ID', align: 'right' },
    { key: 'name', header: 'Variety' },
    { key: 'color', header: 'Color', render: (row) => <ColorSwatch color={row.color} /> },
    { key: 'crop_count', header: 'Crops', align: 'right' },
  ];

  return (
    <CrudPage
      api={varietiesApi}
      title="Rose varieties"
      singular="Variety"
      icon={Flower2}
      description="Rose varieties cultivated by the farm."
      columns={columns}
      searchText={(row) => `${row.name} ${row.color}`}
      emptyForm={{ name: '', color: '' }}
      toForm={(row) => ({ name: row.name, color: row.color })}
      toPayload={(values) => ({ name: normalizeText(values.name), color: normalizeText(values.color) })}
      validate={validateVariety}
      describe={(row) => row.name}
      renderFields={({ values, set, errors }) => (
        <>
          <TextInput label="Variety name" required value={values.name} onChange={(v) => set('name', v)} error={errors.name} maxLength={100} />
          <TextInput
            label="Color"
            required
            value={values.color}
            onChange={(v) => set('color', v)}
            error={errors.color}
            maxLength={50}
            list="rose-colors"
            hint="e.g. Red, White, Pink, Yellow, Bicolor"
          />
          <datalist id="rose-colors">
            {['Red', 'White', 'Pink', 'Yellow', 'Orange', 'Purple', 'Peach', 'Cream', 'Bicolor', 'Lavender'].map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </>
      )}
    />
  );
}
