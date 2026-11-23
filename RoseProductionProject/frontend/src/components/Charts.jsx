import { useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Table2 } from 'lucide-react';
import { EmptyState } from './States.jsx';
import { formatCompact, formatInt, formatNumber, formatShortDate } from '../utils/format.js';

// Validated categorical palette (fixed order, never cycled) - see
// docs/GUI.md "Charts". Slot 1 = primary measure, slot 2 = comparison.
export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'];
const GRID = '#e7e5e0';
const AXIS = '#6b6a66';

const axisProps = {
  tick: { fill: AXIS, fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: GRID },
};

function ChartTooltip({ active, payload, label, labelFormatter, unit = 'stems' }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{labelFormatter ? labelFormatter(label) : label}</strong>
      {payload.map((item) => (
        <div key={item.dataKey} className="tooltip-row">
          <span className="tooltip-key" style={{ background: item.color }} aria-hidden="true" />
          <span>{item.name}</span>
          <span className="tooltip-value">
            {item.value === null || item.value === undefined ? 'no data' : `${formatNumber(item.value)} ${unit}`}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ChartCard({ title, subtitle, children, table, empty, emptyMessage, className = '' }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className={`card chart-card ${className}`}>
      <header className="card-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        {table && !empty && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
            <Table2 size={14} aria-hidden="true" /> {showTable ? 'Chart' : 'Table'}
          </button>
        )}
      </header>
      {empty ? (
        <EmptyState title="No data available" message={emptyMessage} />
      ) : showTable ? (
        <div className="table-scroll chart-table">{table}</div>
      ) : (
        <div className="chart-body">{children}</div>
      )}
    </section>
  );
}

export function SimpleTable({ columns, rows }) {
  return (
    <table className="data-table compact">
      <thead>
        <tr>{columns.map((c) => <th key={c.key} className={c.align === 'right' ? 'align-right' : undefined}>{c.header}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <tr key={index}>
            {columns.map((c) => (
              <td key={c.key} className={c.align === 'right' ? 'align-right' : undefined}>
                {c.render ? c.render(row) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Horizontal bars: one category per row (e.g. production by variety). */
export function HorizontalBars({ data, labelKey = 'label', valueKey = 'total', name = 'Harvested stems', height }) {
  const chartHeight = height || Math.max(180, data.length * 36 + 40);
  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" {...axisProps} tickFormatter={formatCompact} />
        <YAxis type="category" dataKey={labelKey} {...axisProps} width={110} />
        <Tooltip cursor={{ fill: 'rgba(42,120,214,0.08)' }} content={<ChartTooltip />} />
        <Bar dataKey={valueKey} name={name} fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Vertical bars for a handful of categories (e.g. seasons). */
export function VerticalBars({ data, labelKey = 'label', valueKey = 'total', name = 'Harvested stems', height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }} barCategoryGap="30%">
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={labelKey} {...axisProps} interval={0} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={48} />
        <Tooltip cursor={{ fill: 'rgba(42,120,214,0.08)' }} content={<ChartTooltip />} />
        <Bar dataKey={valueKey} name={name} fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={56} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Totals over time on a true time axis. Gaps longer than `gapDays` break the
 * line (no interpolation across periods without harvests).
 */
export function TimeLine({ data, xKey = 'date', valueKey = 'total', name = 'Harvested stems', height = 280, gapDays = 7 }) {
  const isDaily = data.length > 0 && /^\d{4}-\d{2}-\d{2}$/.test(String(data[0][xKey]));
  if (!isDaily) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey={xKey} {...axisProps} />
          <YAxis {...axisProps} tickFormatter={formatCompact} width={48} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: AXIS, strokeDasharray: '3 3' }} />
          <Line type="linear" dataKey={valueKey} name={name} stroke={SERIES[0]} strokeWidth={2}
            dot={{ r: 4, strokeWidth: 2, stroke: '#ffffff', fill: SERIES[0] }} activeDot={{ r: 6, strokeWidth: 2, stroke: '#ffffff' }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }
  const DAY = 86400000;
  const points = [];
  data.forEach((row, index) => {
    const t = Date.parse(`${row[xKey]}T00:00:00Z`);
    if (index > 0) {
      const prev = Date.parse(`${data[index - 1][xKey]}T00:00:00Z`);
      if (t - prev > gapDays * DAY) points.push({ t: prev + DAY, [valueKey]: null, gap: true });
    }
    points.push({ ...row, t });
  });
  const label = (t) => formatShortDate(new Date(t).toISOString().slice(0, 10));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin - 86400000', 'dataMax + 86400000']}
          {...axisProps} tickFormatter={label} minTickGap={28} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={48} />
        <Tooltip content={<ChartTooltip labelFormatter={label} />} cursor={{ stroke: AXIS, strokeDasharray: '3 3' }} />
        <Line
          type="linear"
          dataKey={valueKey}
          name={name}
          stroke={SERIES[0]}
          strokeWidth={2}
          connectNulls={false}
          isAnimationActive={false}
          dot={{ r: 4, strokeWidth: 2, stroke: '#ffffff', fill: SERIES[0] }}
          activeDot={{ r: 6, strokeWidth: 2, stroke: '#ffffff' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Discrete daily totals (one bar per harvest date, dates labelled). */
export function DailyBars({ data, xKey = 'date', valueKey = 'total', name = 'Harvested stems', height = 280 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={xKey} {...axisProps} tickFormatter={formatShortDate} minTickGap={8} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={48} />
        <Tooltip cursor={{ fill: 'rgba(42,120,214,0.08)' }} content={<ChartTooltip labelFormatter={formatShortDate} />} />
        <Bar dataKey={valueKey} name={name} fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Estimated vs actual (two series, grouped bars, legend). */
export function ComparisonBars({ data, height = 280 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }} barGap={2} barCategoryGap="28%">
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="label" {...axisProps} interval={0} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={48} />
        <Tooltip cursor={{ fill: 'rgba(42,120,214,0.08)' }} content={<ChartTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: AXIS }} iconType="square" />
        <Bar dataKey="estimated" name="Estimated" fill={SERIES[1]} radius={[4, 4, 0, 0]} maxBarSize={36} />
        <Bar dataKey="actual" name="Actual" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export { formatInt };
