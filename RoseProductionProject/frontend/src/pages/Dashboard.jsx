import { Link } from 'react-router-dom';
import {
  CalendarRange, Flower2, Home, LayoutGrid, Map, RefreshCw, Scissors, Sprout, TrendingUp, Warehouse,
} from 'lucide-react';
import { statsApi } from '../api/endpoints.js';
import {
  ChartCard, ComparisonBars, DailyBars, HorizontalBars, SimpleTable, VerticalBars,
} from '../components/Charts.jsx';
import { Badge, PageHeader, StatCard } from '../components/Common.jsx';
import { EmptyState, ErrorState, LoadingState } from '../components/States.jsx';
import { useApi } from '../hooks/useApi.js';
import { formatDate, formatInt, formatNumber } from '../utils/format.js';

export default function Dashboard() {
  const { data, loading, error, reload } = useApi(() => statsApi.dashboard(), []);

  if (loading && !data) return <LoadingState label="Loading dashboard…" />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;

  const { counts, production } = data;
  const evaluated = data.forecast_vs_actual.filter((f) => f.actual !== null);
  const pending = data.forecast_vs_actual.filter((f) => f.actual === null);
  const statusText = Object.entries(data.forecast_status).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(' · ');
  const byVariety = [...data.by_variety].sort((a, b) => b.total - a.total);

  return (
    <section className="page">
      <PageHeader
        title="Dashboard"
        icon={Home}
        description={`Live data from RoseProductionDB · ${formatDate(data.today)}`}
        actions={(
          <button type="button" className="btn btn-secondary" onClick={reload} disabled={loading}>
            <RefreshCw size={16} aria-hidden="true" className={loading ? 'spin' : ''} /> Refresh
          </button>
        )}
      />

      <div className="stat-grid">
        <StatCard label="Farms" value={formatInt(counts.farms)} icon={Map} />
        <StatCard label="Lots" value={formatInt(counts.lots)} icon={LayoutGrid} hint={`${formatNumber(data.total_area)} total area`} />
        <StatCard label="Rose varieties" value={formatInt(counts.varieties)} icon={Flower2} />
        <StatCard label="Crops" value={formatInt(counts.crops)} icon={Sprout} />
        <StatCard label="Harvests" value={formatInt(counts.harvests)} icon={Scissors} hint={`records · ${formatInt(counts.seasons)} seasons`} />
        <StatCard
          label="Total stems"
          value={`${formatInt(production.total)}`}
          icon={Warehouse}
          tone="accent"
          hint={production.records ? `avg ${formatNumber(production.average)} · min ${formatInt(production.minimum)} · max ${formatInt(production.maximum)}` : 'no harvests yet'}
        />
        <StatCard label="Forecasts" value={formatInt(counts.forecasts)} icon={TrendingUp} hint={statusText || 'none yet'} />
      </div>

      <div className="grid-2">
        <ChartCard
          title="Production by rose variety"
          subtitle="Total harvested stems per variety"
          empty={byVariety.length === 0}
          emptyMessage="Register harvests to see production by variety."
          table={(
            <SimpleTable
              columns={[
                { key: 'label', header: 'Variety' },
                { key: 'total', header: 'Total', align: 'right', render: (r) => formatInt(r.total) },
                { key: 'records', header: 'Records', align: 'right' },
                { key: 'average', header: 'Average', align: 'right', render: (r) => formatNumber(r.average) },
              ]}
              rows={byVariety}
            />
          )}
        >
          <HorizontalBars data={byVariety} />
        </ChartCard>

        <ChartCard
          title="Production by season"
          subtitle="Total harvested stems per commercial season"
          empty={data.by_season.length === 0}
          emptyMessage="No harvests are linked to seasons yet."
          table={(
            <SimpleTable
              columns={[
                { key: 'label', header: 'Season' },
                { key: 'start_date', header: 'Start' },
                { key: 'end_date', header: 'End' },
                { key: 'total', header: 'Total', align: 'right', render: (r) => formatInt(r.total) },
                { key: 'records', header: 'Records', align: 'right' },
              ]}
              rows={data.by_season}
            />
          )}
        >
          <VerticalBars data={data.by_season} />
        </ChartCard>
      </div>

      <ChartCard
        title="Harvest quantities over time"
        subtitle="Stems harvested on each harvest date (all crops); days without harvests are omitted"
        empty={data.over_time.length === 0}
        emptyMessage="No harvest records yet."
        table={(
          <SimpleTable
            columns={[
              { key: 'date', header: 'Date', render: (r) => formatDate(r.date) },
              { key: 'total', header: 'Stems', align: 'right', render: (r) => formatInt(r.total) },
              { key: 'records', header: 'Records', align: 'right' },
            ]}
            rows={data.over_time}
          />
        )}
      >
        <DailyBars data={data.over_time} />
      </ChartCard>

      <div className="grid-2">
        <ChartCard
          title="Forecast vs actual production"
          subtitle={`${evaluated.length} evaluated · ${pending.length} pending (no matching harvest yet)`}
          empty={evaluated.length === 0}
          emptyMessage={data.forecast_vs_actual.length
            ? 'No forecast can be evaluated yet: none has a real harvest for the same crop and date.'
            : 'No forecasts have been registered.'}
          table={(
            <SimpleTable
              columns={[
                { key: 'label', header: 'Forecast' },
                { key: 'estimated', header: 'Estimated', align: 'right', render: (r) => formatNumber(r.estimated) },
                { key: 'actual', header: 'Actual', align: 'right', render: (r) => formatInt(r.actual) },
                { key: 'diff', header: 'Abs. error', align: 'right', render: (r) => formatNumber(Math.abs(r.actual - r.estimated)) },
              ]}
              rows={evaluated}
            />
          )}
        >
          <ComparisonBars data={evaluated.map((f) => ({ ...f, label: `#${f.forecast_id}` }))} />
        </ChartCard>

        <section className="card">
          <header className="card-header">
            <div>
              <h2>Upcoming seasons</h2>
              <p className="muted small">Active or starting after today</p>
            </div>
            <Link to="/seasons" className="btn btn-ghost btn-sm"><CalendarRange size={14} aria-hidden="true" /> Seasons</Link>
          </header>
          {data.upcoming_seasons.length === 0 ? (
            <EmptyState title="No upcoming seasons" message="Create the next commercial season (e.g. Valentine's Day 2027) to plan harvests and forecasts." />
          ) : (
            <ul className="season-list">
              {data.upcoming_seasons.map((season) => (
                <li key={season.season_id}>
                  <div>
                    <strong>{season.name}</strong>
                    <span className="muted small">{formatDate(season.start_date)} – {formatDate(season.end_date)}</span>
                  </div>
                  {season.status === 'active'
                    ? <Badge tone="success">Active now</Badge>
                    : <Badge tone="info">in {season.days_until_start} days</Badge>}
                </li>
              ))}
            </ul>
          )}
          {pending.length > 0 && (
            <>
              <h3 className="subheading">Pending forecasts</h3>
              <ul className="season-list">
                {pending.slice(0, 6).map((f) => (
                  <li key={f.forecast_id}>
                    <div>
                      <strong>{f.label}</strong>
                      <span className="muted small">Estimated {formatNumber(f.estimated)} stems</span>
                    </div>
                    <Badge tone="warning">Pending</Badge>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
