import { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { statsApi } from '../api/endpoints.js';
import { ChartCard, HorizontalBars, SimpleTable, TimeLine, VerticalBars } from '../components/Charts.jsx';
import { FilterBar, FilterDate, FilterSelect, PageHeader, StatCard } from '../components/Common.jsx';
import { ErrorState, LoadingState } from '../components/States.jsx';
import { useApi } from '../hooks/useApi.js';
import { toOptions, useLookups } from '../hooks/useLookups.js';
import { formatInt, formatNumber } from '../utils/format.js';

const GROUPS = [
  { value: 'variety', label: 'Rose variety' },
  { value: 'lot', label: 'Lot' },
  { value: 'season', label: 'Season' },
  { value: 'crop', label: 'Crop' },
  { value: 'month', label: 'Month' },
  { value: 'date', label: 'Date' },
];
const EMPTY_FILTERS = { date_from: '', date_to: '', variety_id: '', lot_id: '', season_id: '', crop_id: '' };

export default function Analytics() {
  const lookups = useLookups(['varieties', 'lots', 'seasons', 'crops']);
  const [groupBy, setGroupBy] = useState('variety');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const setFilter = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  const { data, loading, error, reload } = useApi(
    () => statsApi.production({ group_by: groupBy, ...filters }),
    [groupBy, JSON.stringify(filters)],
  );

  const groupLabel = GROUPS.find((g) => g.value === groupBy)?.label;
  const groups = data?.groups || [];
  const isTime = groupBy === 'date' || groupBy === 'month';

  return (
    <section className="page">
      <PageHeader
        title="Production analysis"
        icon={BarChart3}
        description="Historical production statistics (total, average, minimum, maximum) by date, variety, lot and season."
      />
      <FilterBar onReset={() => setFilters(EMPTY_FILTERS)} active={Object.values(filters).some(Boolean)}>
        <label className="filter-control">
          <span>Group by</span>
          <select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}>
            {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </label>
        <FilterDate label="From" value={filters.date_from} onChange={setFilter('date_from')} />
        <FilterDate label="To" value={filters.date_to} onChange={setFilter('date_to')} />
        <FilterSelect label="Variety" value={filters.variety_id} onChange={setFilter('variety_id')} options={toOptions.varieties(lookups.data?.varieties)} allLabel="All varieties" />
        <FilterSelect label="Lot" value={filters.lot_id} onChange={setFilter('lot_id')} options={toOptions.lots(lookups.data?.lots)} allLabel="All lots" />
        <FilterSelect label="Season" value={filters.season_id} onChange={setFilter('season_id')} options={toOptions.seasons(lookups.data?.seasons)} allLabel="All seasons" />
        <FilterSelect label="Crop" value={filters.crop_id} onChange={setFilter('crop_id')} options={toOptions.crops(lookups.data?.crops)} allLabel="All crops" />
      </FilterBar>

      {loading && !data ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {data && !error && (
        <>
          <div className="stat-grid stat-grid-5">
            <StatCard label="Total stems" value={formatInt(data.overall.total)} tone="accent" />
            <StatCard label="Harvest records" value={formatInt(data.overall.records)} />
            <StatCard label="Average per record" value={formatNumber(data.overall.average)} />
            <StatCard label="Minimum" value={formatInt(data.overall.minimum)} />
            <StatCard label="Maximum" value={formatInt(data.overall.maximum)} />
          </div>
          <ChartCard
            title={`Total production by ${groupLabel.toLowerCase()}`}
            subtitle="Sum of harvested stems for the selected filters"
            empty={groups.length === 0}
            emptyMessage="No harvest records match the selected filters."
          >
            {isTime
              ? <TimeLine data={groups} xKey="key" />
              : groups.length > 6
                ? <HorizontalBars data={groups} />
                : <VerticalBars data={groups} />}
          </ChartCard>
          <section className="card">
            <header className="card-header"><h2>Statistics by {groupLabel.toLowerCase()}</h2></header>
            {groups.length === 0 ? (
              <p className="muted">No data.</p>
            ) : (
              <div className="table-scroll">
                <SimpleTable
                  columns={[
                    { key: 'label', header: groupLabel },
                    { key: 'records', header: 'Records', align: 'right' },
                    { key: 'total', header: 'Total', align: 'right', render: (r) => formatInt(r.total) },
                    { key: 'average', header: 'Average', align: 'right', render: (r) => formatNumber(r.average) },
                    { key: 'minimum', header: 'Minimum', align: 'right', render: (r) => formatInt(r.minimum) },
                    { key: 'maximum', header: 'Maximum', align: 'right', render: (r) => formatInt(r.maximum) },
                  ]}
                  rows={groups}
                />
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
