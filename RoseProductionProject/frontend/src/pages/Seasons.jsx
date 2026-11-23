import { CalendarRange } from 'lucide-react';
import { seasonsApi } from '../api/endpoints.js';
import { Badge } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { TextInput } from '../components/FormField.jsx';
import { formatDate, formatInt, seasonStatus } from '../utils/format.js';
import {
  findClash, normalizeText, rules, runRules, textKey, withDuplicate,
} from '../utils/validation.js';

const schema = {
  name: [rules.required('Season name'), rules.maxLength('Season name', 100)],
  start_date: [rules.required('Start date'), rules.date('Start date')],
  end_date: [
    rules.required('End date'),
    rules.date('End date'),
    (value, values) => (values.start_date && value && value < values.start_date
      ? 'End date must be on or after the start date' : null),
  ],
};

// Same name with an overlapping period = the same season registered twice
// (the same name for another period, e.g. next year, is allowed).
export function validateSeason(values, { rows, editing } = {}) {
  const overlaps = (row) => textKey(row.name) === textKey(values.name)
    && values.start_date && values.end_date
    && row.start_date <= values.end_date && row.end_date >= values.start_date;
  const clash = findClash({
    rows,
    idKey: 'season_id',
    editing,
    unchanged: editing && textKey(editing.name) === textKey(values.name)
      && editing.start_date === values.start_date && editing.end_date === values.end_date,
    sameAs: overlaps,
  });
  return withDuplicate(runRules(values, schema), 'name', clash,
    'A season with this name already exists for an overlapping period.');
}

const STATUS_TONE = { active: 'success', upcoming: 'info', past: 'neutral' };

export default function Seasons() {
  const columns = [
    { key: 'season_id', header: 'ID', align: 'right' },
    { key: 'name', header: 'Season' },
    { key: 'start_date', header: 'Start', render: (row) => formatDate(row.start_date) },
    { key: 'end_date', header: 'End', render: (row) => formatDate(row.end_date) },
    { key: 'duration_days', header: 'Days', align: 'right' },
    {
      key: 'status',
      header: 'Status',
      sortValue: (row) => seasonStatus(row),
      render: (row) => {
        const status = seasonStatus(row);
        return <Badge tone={STATUS_TONE[status]}>{status[0].toUpperCase() + status.slice(1)}</Badge>;
      },
    },
    { key: 'harvest_count', header: 'Harvests', align: 'right', render: (row) => formatInt(row.harvest_count) },
    { key: 'forecast_count', header: 'Forecasts', align: 'right', render: (row) => formatInt(row.forecast_count) },
  ];

  return (
    <CrudPage
      api={seasonsApi}
      title="Seasons"
      singular="Season"
      icon={CalendarRange}
      description="Commercial and production seasons such as Valentine's Day and Mother's Day."
      columns={columns}
      initialSort={{ key: 'start_date', dir: 'asc' }}
      searchText={(row) => `${row.name} ${row.start_date} ${row.end_date}`}
      emptyForm={{ name: '', start_date: '', end_date: '' }}
      toForm={(row) => ({ name: row.name, start_date: row.start_date, end_date: row.end_date })}
      toPayload={(values) => ({ name: normalizeText(values.name), start_date: values.start_date, end_date: values.end_date })}
      validate={validateSeason}
      describe={(row) => row.name}
      formDescription="Harvest and forecast dates must fall inside the season's date range."
      renderFields={({ values, set, errors }) => (
        <>
          <TextInput label="Season name" required value={values.name} onChange={(v) => set('name', v)} error={errors.name} maxLength={100} />
          <div className="form-row">
            <TextInput label="Start date" required type="date" value={values.start_date} onChange={(v) => set('start_date', v)} error={errors.start_date} />
            <TextInput label="End date" required type="date" min={values.start_date || undefined} value={values.end_date} onChange={(v) => set('end_date', v)} error={errors.end_date} />
          </div>
        </>
      )}
    />
  );
}
