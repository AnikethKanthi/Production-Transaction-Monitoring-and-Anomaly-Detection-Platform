import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getMetrics, type MetricsResponse } from '../api/metrics';
import {
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
  PageHeading,
  Panel,
  money,
  number,
  percent,
} from '../components/ui';

const colors = ['#428978', '#dc9d66', '#b96b72', '#8895ac'];
const timeLabel = (value: string) =>
  new Date(value).toLocaleString('en-US', {
    timeZone: 'UTC',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
  });

function Charts({ data }: { data: MetricsResponse }) {
  const summary = data.overall;
  const statuses = [
    { name: 'Completed', value: summary.success_rate },
    { name: 'Failed', value: summary.decline_rate },
    { name: 'Refunded', value: summary.refund_rate },
    {
      name: 'Pending',
      value: Math.max(
        0,
        1 - summary.success_rate - summary.decline_rate - summary.refund_rate,
      ),
    },
  ];
  const step = data.interval === 'hour' ? 3_600_000 : 86_400_000;
  const first = Math.floor(Date.parse(data.start) / step) * step;
  const buckets = new Map(
    data.time_series.map((row) => [Date.parse(row.label), row]),
  );
  const points = Array.from(
    {
      length: Math.min(1000, Math.ceil((Date.parse(data.end) - first) / step)),
    },
    (_, index) => {
      const timestamp = first + index * step;
      const item = buckets.get(timestamp);
      return {
        label: new Date(timestamp).toISOString(),
        volume: item?.transaction_count ?? 0,
        anomaly: item ? item.anomaly_rate * 100 : null,
      };
    },
  );
  return (
    <>
      <div className="charts-grid">
        <Panel
          title="Transaction volume"
          subtitle={`${data.interval === 'hour' ? 'Hourly' : 'Daily'} activity · UTC`}
        >
          <div
            className="chart"
            role="img"
            aria-label={`Transaction volume chart: ${number(summary.transaction_count)} transactions across the selected period`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={points}
                margin={{ top: 16, right: 12, left: -22, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="volume-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#428978" stopOpacity={0.22} />
                    <stop
                      offset="100%"
                      stopColor="#428978"
                      stopOpacity={0.01}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 5"
                  vertical={false}
                  stroke="#e6ecef"
                />
                <XAxis
                  dataKey="label"
                  tickFormatter={timeLabel}
                  minTickGap={65}
                  tickLine={false}
                  axisLine={false}
                  fontSize={10}
                />
                <YAxis
                  allowDecimals={false}
                  tickLine={false}
                  axisLine={false}
                  fontSize={11}
                />
                <Tooltip labelFormatter={(label) => timeLabel(String(label))} />
                <Area
                  name="Transactions"
                  type="linear"
                  dataKey="volume"
                  stroke="#428978"
                  fill="url(#volume-fill)"
                  strokeWidth={2.5}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Status distribution" subtitle="Share of transactions">
          <div
            className="donut"
            role="img"
            aria-label={`Status distribution: ${statuses.map((row) => `${row.name} ${percent(row.value)}`).join(', ')}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statuses}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="65%"
                  outerRadius="90%"
                  paddingAngle={3}
                  isAnimationActive={false}
                >
                  {statuses.map((row, index) => (
                    <Cell key={row.name} fill={colors[index]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => percent(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-label">
              <strong>{percent(summary.success_rate)}</strong>
              <span>success rate</span>
            </div>
          </div>
          <ul className="legend">
            {statuses.map((row, index) => (
              <li key={row.name}>
                <span>
                  <i style={{ background: colors[index] }} />
                  {row.name}
                </span>
                <strong>{percent(row.value)}</strong>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <div className="charts-grid lower-grid">
        <Panel
          title="Anomaly rate"
          subtitle="Positive model scores · not alert volume"
        >
          <div
            className="chart small-chart"
            role="img"
            aria-label={`Anomaly rate chart: overall ${percent(summary.anomaly_rate)}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={points}
                margin={{ top: 18, right: 16, left: -12, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 5"
                  vertical={false}
                  stroke="#e6ecef"
                />
                <XAxis
                  dataKey="label"
                  tickFormatter={timeLabel}
                  minTickGap={65}
                  axisLine={false}
                  tickLine={false}
                  fontSize={10}
                />
                <YAxis
                  unit="%"
                  domain={[0, 'auto']}
                  axisLine={false}
                  tickLine={false}
                  fontSize={11}
                />
                <Tooltip
                  labelFormatter={(label) => timeLabel(String(label))}
                  formatter={(value) => `${Number(value).toFixed(1)}%`}
                />
                <Line
                  type="linear"
                  name="Anomaly rate"
                  dataKey="anomaly"
                  stroke="#b96b72"
                  strokeWidth={2.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-note">
            Gaps indicate periods with no transactions.
          </p>
        </Panel>
        <Panel title="Country activity" subtitle={data.currency}>
          <div className="country-list">
            {data.by_country.length ? (
              data.by_country.map((row) => (
                <div className="country-row" key={row.label}>
                  <div>
                    <strong>{row.label}</strong>
                    <span>{number(row.transaction_count)} transactions</span>
                  </div>
                  <strong>
                    {money(row.transaction_amount, data.currency)}
                  </strong>
                  <div className="bar-track">
                    <div
                      style={{
                        width: `${summary.transaction_count ? (row.transaction_count / summary.transaction_count) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                title="No country data"
                description="Country activity appears once transactions are available."
              />
            )}
          </div>
        </Panel>
      </div>
      <details className="accessible-data">
        <summary>View chart data as a table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Bucket (UTC)</th>
                <th scope="col">Transactions</th>
                <th scope="col">Anomaly rate</th>
              </tr>
            </thead>
            <tbody>
              {points.map((row) => (
                <tr key={row.label}>
                  <td>{timeLabel(row.label)}</td>
                  <td>{number(row.volume)}</td>
                  <td>
                    {row.anomaly === null
                      ? 'No transactions'
                      : `${row.anomaly.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

export default function DashboardPage() {
  const [hours, setHours] = useState(24);
  const [currency, setCurrency] = useState('USD');
  const query = useQuery({
    queryKey: ['metrics', hours, currency],
    queryFn: ({ signal }) => getMetrics(hours, currency, signal),
    refetchInterval: 30_000,
  });
  const data = query.data;
  return (
    <>
      <PageHeading
        title="Transaction overview"
        description="A clear view of your payments, performance, and emerging risk."
      >
        <button
          className="secondary"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          {query.isFetching ? 'Refreshing…' : '↻ Refresh data'}
        </button>
      </PageHeading>
      <div className="toolbar">
        <div className="range-control" role="group" aria-label="Time range">
          {[
            [24, '24 hours'],
            [168, '7 days'],
            [720, '30 days'],
          ].map(([value, label]) => (
            <button
              key={value}
              aria-pressed={hours === value}
              onClick={() => setHours(Number(value))}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="currency-control">
          Currency{' '}
          <select
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {['USD', 'GBP', 'EUR', 'CAD'].map((code) => (
              <option key={code}>{code}</option>
            ))}
          </select>
        </label>
      </div>
      {query.isPending && <LoadingState />}
      {query.isError && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {data && (
        <>
          <div className="data-meta">
            <span>
              {query.isError
                ? 'Last successful data · refresh failed'
                : query.isFetching
                  ? 'Updating live data…'
                  : 'Live API data'}{' '}
              ·{' '}
              {data.source === 'cache'
                ? 'Cached aggregate'
                : 'Database aggregate'}
            </span>
            <span>
              As of{' '}
              {new Date(data.end).toLocaleString('en-US', { timeZone: 'UTC' })}{' '}
              UTC
            </span>
          </div>
          <div className="kpi-grid">
            <KpiCard
              label="Total transactions"
              value={number(data.overall.transaction_count)}
              note="Across the selected period"
              accent
            />
            <KpiCard
              label="Transaction amount"
              value={money(data.overall.transaction_amount, currency)}
              note={`${money(data.overall.average_transaction_amount, currency)} average amount`}
            />
            <KpiCard
              label="Success rate"
              value={percent(data.overall.success_rate)}
              note={`${percent(data.overall.decline_rate)} declined · ${percent(data.overall.refund_rate)} refunded`}
            />
            <KpiCard
              label="Anomaly rate"
              value={percent(data.overall.anomaly_rate)}
              note={`${data.overall.average_processing_latency_ms.toFixed(1)} ms avg. inference latency`}
            />
          </div>
          {data.overall.transaction_count === 0 ? (
            <Panel title="Activity">
              <EmptyState />
            </Panel>
          ) : (
            <Charts data={data} />
          )}
        </>
      )}
    </>
  );
}
