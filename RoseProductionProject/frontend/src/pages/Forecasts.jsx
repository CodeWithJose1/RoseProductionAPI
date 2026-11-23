import { useMemo, useRef, useState } from 'react';
import { Calculator, Save, TrendingUp, Wand2 } from 'lucide-react';
import { forecastsApi } from '../api/endpoints.js';
import { Badge, FilterBar, FilterDate, FilterSelect } from '../components/Common.jsx';
import { CrudPage } from '../components/CrudPage.jsx';
import { SelectInput, TextInput } from '../components/FormField.jsx';
import { Modal } from '../components/Modal.jsx';
import { InlineError, Spinner } from '../components/States.jsx';
import { useToast } from '../context/ToastContext.jsx';
import { useApi } from '../hooks/useApi.js';
import { toOptions, useLookups } from '../hooks/useLookups.js';
import { formatDate, formatInt, formatNumber } from '../utils/format.js';
import {
  dateWithin, findClash, normalizeText, rules, runRules, withDuplicate,
} from '../utils/validation.js';

const EMPTY_FILTERS = { crop_id: '', variety_id: '', season_id: '', date_from: '', date_to: '' };

/** Normalises the vw_forecast_status row attached by the API. */
export function evaluationOf(forecast) {
  const row = forecast.evaluation || {};
  const actual = row.actual_quantity ?? null;
  const evaluated = actual !== null && actual !== undefined;
  const estimated = forecast.estimated_quantity;
  const absoluteError = row.absolute_error ?? (evaluated ? Math.abs(actual - estimated) : null);
  const percentError = row.percentage_error ?? row.ape ?? row.absolute_percentage_error
    ?? (evaluated && actual !== 0 ? (Math.abs(actual - estimated) / actual) * 100 : null);
  return {
    evaluated,
    status: row.status || row.forecast_status || (evaluated ? 'Evaluated' : 'Pending'),
    actual,
    absoluteError,
    percentError,
  };
}

function StatusBadge({ forecast }) {
  const ev = evaluationOf(forecast);
  return <Badge tone={ev.evaluated ? 'success' : 'warning'}>{ev.status}</Badge>;
}

function SummaryPanel({ refreshToken }) {
  const { data, error } = useApi(() => forecastsApi.summary(), [refreshToken]);
  if (error || !data || data.length === 0) return null;
  const columns = Object.keys(data[0]);
  return (
    <section className="card">
      <header className="card-header">
        <h2>Forecast summary</h2>
        <span className="muted">Database view <code>vw_forecast_summary</code></span>
      </header>
      <div className="table-scroll">
        <table className="data-table compact">
          <thead><tr>{columns.map((c) => <th key={c}>{c.replaceAll('_', ' ')}</th>)}</tr></thead>
          <tbody>
            {data.map((row, index) => (
              // eslint-disable-next-line react/no-array-index-key
              <tr key={index}>
                {columns.map((c) => (
                  <td key={c}>{typeof row[c] === 'number' ? formatNumber(row[c]) : String(row[c] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function GenerateForecastModal({ open, onClose, onSaved, crops, seasons }) {
  const toast = useToast();
  const [values, setValues] = useState({ crop_id: '', season_id: '', forecast_date: '', window: '3' });
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [busy, setBusy] = useState(null); // 'calc' | 'save'
  const inFlight = useRef(false); // blocks a second request before re-render

  const seasonById = useMemo(() => Object.fromEntries(seasons.map((s) => [String(s.season_id), s])), [seasons]);
  const cropById = useMemo(() => Object.fromEntries(crops.map((c) => [String(c.crop_id), c])), [crops]);
  const season = seasonById[values.season_id];
  const selectedCrop = cropById[values.crop_id];

  const schema = {
    crop_id: [rules.required('Crop')],
    season_id: [rules.required('Season')],
    forecast_date: [
      rules.required('Forecast date'),
      rules.date('Forecast date'),
      (value) => (season && value && !dateWithin(value, season.start_date, season.end_date)
        ? `The date must be inside ${season.name} (${season.start_date} to ${season.end_date})` : null),
      (value) => (selectedCrop && value && value < selectedCrop.planting_date
        ? `The date must be on or after the crop's planting date (${selectedCrop.planting_date})` : null),
    ],
    window: [
      rules.required('Window'),
      (value) => (Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 12
        ? null : 'Window must be a whole number between 1 and 12'),
    ],
  };

  const set = (field, value) => {
    setValues((v) => ({ ...v, [field]: value }));
    setResult(null);
    setApiError(null);
  };

  const reset = () => {
    setValues({ crop_id: '', season_id: '', forecast_date: '', window: '3' });
    setErrors({});
    setResult(null);
    setApiError(null);
  };

  const run = async (save) => {
    const found = runRules(values, schema);
    setErrors(found);
    if (Object.keys(found).length) return;
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(save ? 'save' : 'calc');
    setApiError(null);
    try {
      const response = await forecastsApi.generate({
        crop_id: Number(values.crop_id),
        season_id: Number(values.season_id),
        forecast_date: values.forecast_date,
        window: Number(values.window),
        save,
      });
      setResult({ ...response.calculation, forecast_id: response.forecast?.forecast_id });
      if (save) {
        toast.success(`Forecast #${response.forecast.forecast_id} saved (${formatNumber(response.forecast.estimated_quantity)} stems)`);
        onSaved(response.forecast);
      }
    } catch (error) {
      setApiError(error);
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  };

  return (
    <Modal
      open={open}
      size="lg"
      title="Generate forecast"
      description="Moving average of the most recent harvests of the selected crop before the forecast date."
      onClose={busy ? undefined : () => { reset(); onClose(); }}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={() => { reset(); onClose(); }} disabled={Boolean(busy)}>{result?.saved ? 'Close' : 'Cancel'}</button>
          <button type="button" className="btn btn-secondary" onClick={() => run(false)} disabled={Boolean(busy)}>
            {busy === 'calc' ? <Spinner size={16} /> : <Calculator size={16} aria-hidden="true" />} Calculate estimate
          </button>
          <button type="button" className="btn btn-primary" onClick={() => run(true)} disabled={Boolean(busy) || !result || result.saved || Boolean(result.existing_forecast_id)}>
            {busy === 'save' ? <Spinner size={16} /> : <Save size={16} aria-hidden="true" />} Save forecast
          </button>
        </>
      )}
    >
      <div className="form-grid">
        <SelectInput label="Crop" required value={values.crop_id} onChange={(v) => set('crop_id', v)} options={toOptions.crops(crops)} error={errors.crop_id} />
        <SelectInput label="Season" required value={values.season_id} onChange={(v) => set('season_id', v)} options={toOptions.seasons(seasons)} error={errors.season_id} />
        <div className="form-row">
          <TextInput
            label="Forecast date"
            required
            type="date"
            min={season?.start_date}
            max={season?.end_date}
            value={values.forecast_date}
            onChange={(v) => set('forecast_date', v)}
            error={errors.forecast_date}
            hint={season ? `Allowed: ${season.start_date} to ${season.end_date}` : 'Select a season first'}
          />
          <TextInput
            label="Harvests in the average (N)"
            required
            type="number"
            min="1"
            max="12"
            step="1"
            value={values.window}
            onChange={(v) => set('window', v)}
            error={errors.window}
            hint="Project method: 3 previous harvests"
          />
        </div>
        {apiError && <div className="form-span"><InlineError error={apiError} /></div>}
        {result && (
          <div className="form-span forecast-result" aria-live="polite">
            <div className="forecast-figure">
              <span className="muted">Estimated production</span>
              <strong>{formatNumber(result.estimated_quantity)} stems</strong>
              <span className="muted">{result.method}</span>
            </div>
            <div>
              <p className="formula"><code>{result.formula}</code></p>
              <div className="table-scroll">
              <table className="data-table compact">
                <caption className="sr-only">Harvests used in the calculation</caption>
                <thead><tr><th>Harvest</th><th>Date</th><th>Season</th><th className="align-right">Stems</th></tr></thead>
                <tbody>
                  {result.history.map((h) => (
                    <tr key={h.harvest_id}>
                      <td>#{h.harvest_id}</td><td>{formatDate(h.harvest_date)}</td><td>{h.season}</td>
                      <td className="align-right">{formatInt(h.quantity)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              {result.saved ? <Badge tone="success">Saved as forecast #{result.forecast_id}</Badge> : result.existing_forecast_id ? (
                <p className="field-error" role="alert">This forecast already exists for the selected crop and date (forecast #{result.existing_forecast_id}). It cannot be saved again; edit the existing forecast in the table instead.</p>
              ) : <p className="muted small">Not saved yet — review and press “Save forecast”.</p>}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default function Forecasts() {
  const lookups = useLookups(['crops', 'seasons', 'varieties']);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const setFilter = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  const seasons = lookups.data?.seasons || [];
  const crops = lookups.data?.crops || [];
  const seasonById = useMemo(() => Object.fromEntries(seasons.map((s) => [String(s.season_id), s])), [seasons]);
  const cropById = useMemo(() => Object.fromEntries(crops.map((c) => [String(c.crop_id), c])), [crops]);

  const schema = {
    crop_id: [rules.required('Crop')],
    season_id: [rules.required('Season')],
    forecast_date: [
      rules.required('Forecast date'),
      rules.date('Forecast date'),
      (value, values) => {
        const season = seasonById[values.season_id];
        return season && value && !dateWithin(value, season.start_date, season.end_date)
          ? `The date must be inside ${season.name} (${season.start_date} to ${season.end_date})` : null;
      },
      (value, values) => {
        const crop = cropById[values.crop_id];
        return crop && value && value < crop.planting_date
          ? `The date must be on or after the crop's planting date (${crop.planting_date})` : null;
      },
    ],
    estimated_quantity: [rules.required('Estimated quantity'), rules.nonNegativeNumber('Estimated quantity', 9999999999.99)],
    method: [rules.required('Method'), rules.maxLength('Method', 100)],
  };

  const columns = [
    { key: 'forecast_id', header: 'ID', align: 'right' },
    { key: 'forecast_date', header: 'Date', render: (row) => formatDate(row.forecast_date) },
    { key: 'variety', header: 'Crop', render: (row) => `#${row.crop.crop_id} · ${row.crop.variety}`, sortValue: (row) => row.crop.variety },
    { key: 'season', header: 'Season', render: (row) => row.season.name, sortValue: (row) => row.season.name },
    { key: 'estimated_quantity', header: 'Estimated', align: 'right', render: (row) => formatNumber(row.estimated_quantity) },
    { key: 'actual', header: 'Actual', align: 'right', sortValue: (row) => evaluationOf(row).actual, render: (row) => formatInt(evaluationOf(row).actual) },
    {
      key: 'error', header: 'Abs. error', align: 'right',
      sortValue: (row) => evaluationOf(row).absoluteError,
      render: (row) => {
        const ev = evaluationOf(row);
        if (!ev.evaluated) return <span className="muted">—</span>;
        return `${formatNumber(ev.absoluteError)}${ev.percentError !== null ? ` (${formatNumber(ev.percentError)}%)` : ''}`;
      },
    },
    { key: 'status', header: 'Status', sortValue: (row) => evaluationOf(row).status, render: (row) => <StatusBadge forecast={row} /> },
    { key: 'method', header: 'Method', wrap: true },
  ];

  const bump = () => setRefreshToken((n) => n + 1);

  return (
    <>
      <CrudPage
        api={forecastsApi}
        title="Forecasts"
        singular="Forecast"
        icon={TrendingUp}
        description="Estimated production per crop and date. A forecast is evaluated only when a real harvest exists for the same crop and date."
        params={filters}
        refreshToken={refreshToken}
        onChanged={bump}
        initialSort={{ key: 'forecast_date', dir: 'asc' }}
        formSize="lg"
        extraActions={(
          <button type="button" className="btn btn-secondary" onClick={() => setGenerateOpen(true)}>
            <Wand2 size={16} aria-hidden="true" /> Generate forecast
          </button>
        )}
        filters={(
          <FilterBar onReset={() => setFilters(EMPTY_FILTERS)} active={Object.values(filters).some(Boolean)}>
            <FilterSelect label="Crop" value={filters.crop_id} onChange={setFilter('crop_id')} options={toOptions.crops(crops)} allLabel="All crops" />
            <FilterSelect label="Variety" value={filters.variety_id} onChange={setFilter('variety_id')} options={toOptions.varieties(lookups.data?.varieties)} allLabel="All varieties" />
            <FilterSelect label="Season" value={filters.season_id} onChange={setFilter('season_id')} options={toOptions.seasons(seasons)} allLabel="All seasons" />
            <FilterDate label="From" value={filters.date_from} onChange={setFilter('date_from')} />
            <FilterDate label="To" value={filters.date_to} onChange={setFilter('date_to')} />
          </FilterBar>
        )}
        beforeTable={<SummaryPanel refreshToken={refreshToken} />}
        filtersActive={Object.values(filters).some(Boolean)}
      columns={columns}
        searchText={(row) => `${row.forecast_id} ${row.crop.variety} ${row.crop.lot} ${row.season.name} ${row.forecast_date} ${row.method}`}
        emptyForm={{ crop_id: '', season_id: '', forecast_date: '', estimated_quantity: '', method: 'Manual estimate' }}
        toForm={(row) => ({
          crop_id: String(row.crop.crop_id), season_id: String(row.season.season_id), forecast_date: row.forecast_date,
          estimated_quantity: String(row.estimated_quantity), method: row.method,
        })}
        toPayload={(values) => ({
          crop_id: Number(values.crop_id), season_id: Number(values.season_id), forecast_date: values.forecast_date,
          estimated_quantity: Number(values.estimated_quantity), method: normalizeText(values.method),
        })}
        validate={(values, { rows, editing } = {}) => {
          // One forecast per crop and date (UNIQUE unique_crop_forecast_date).
          const sameKey = (cropId, date) => String(cropId) === String(values.crop_id) && date === values.forecast_date;
          const clash = findClash({
            rows,
            idKey: 'forecast_id',
            editing,
            unchanged: editing && sameKey(editing.crop.crop_id, editing.forecast_date),
            sameAs: (row) => sameKey(row.crop.crop_id, row.forecast_date),
          });
          return withDuplicate(runRules(values, schema), 'forecast_date', clash,
            'This forecast already exists for the selected crop and date.');
        }}
        describe={(row) => `Forecast #${row.forecast_id} (${row.crop.variety}, ${row.forecast_date})`}
        formDescription="Use “Generate forecast” to compute the estimate from historical harvests, or enter a manual estimate here."
        renderFields={({ values, set, errors }) => {
          const season = seasonById[values.season_id];
          return (
            <>
              <SelectInput label="Crop" required value={values.crop_id} onChange={(v) => set('crop_id', v)} options={toOptions.crops(crops)} error={errors.crop_id} />
              <SelectInput label="Season" required value={values.season_id} onChange={(v) => set('season_id', v)} options={toOptions.seasons(seasons)} error={errors.season_id} />
              <div className="form-row">
                <TextInput label="Forecast date" required type="date" min={season?.start_date} max={season?.end_date} value={values.forecast_date} onChange={(v) => set('forecast_date', v)} error={errors.forecast_date} hint={season ? `Allowed: ${season.start_date} to ${season.end_date}` : 'Select a season first'} />
                <TextInput label="Estimated quantity" required type="number" min="0" step="0.01" value={values.estimated_quantity} onChange={(v) => set('estimated_quantity', v)} error={errors.estimated_quantity} hint="Zero or more stems" />
              </div>
              <TextInput label="Method" required value={values.method} onChange={(v) => set('method', v)} error={errors.method} maxLength={100} />
            </>
          );
        }}
      />
      <GenerateForecastModal
        open={generateOpen}
        crops={crops}
        seasons={seasons}
        onClose={() => setGenerateOpen(false)}
        onSaved={bump}
      />
    </>
  );
}
