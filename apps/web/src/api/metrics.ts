import { apiGet, ApiError } from './client';

export interface MetricSummary {
  label: string;
  transaction_count: number;
  transaction_amount: number;
  average_transaction_amount: number;
  success_rate: number;
  decline_rate: number;
  refund_rate: number;
  anomaly_rate: number;
  average_processing_latency_ms: number;
}
export interface MetricsResponse {
  start: string;
  end: string;
  interval: 'hour' | 'day';
  currency: string;
  source: string;
  overall: MetricSummary;
  by_country: MetricSummary[];
  by_payment_method: MetricSummary[];
  time_series: MetricSummary[];
}
function isSummary(value: unknown): value is MetricSummary {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.label === 'string' &&
    [
      'transaction_count',
      'transaction_amount',
      'average_transaction_amount',
      'success_rate',
      'decline_rate',
      'refund_rate',
      'anomaly_rate',
      'average_processing_latency_ms',
    ].every(
      (key) =>
        typeof row[key] === 'number' &&
        Number.isFinite(row[key]) &&
        Number(row[key]) >= 0,
    ) &&
    ['success_rate', 'decline_rate', 'refund_rate', 'anomaly_rate'].every(
      (key) => Number(row[key]) <= 1,
    )
  );
}
export async function getMetrics(
  hours: number,
  currency: string,
  signal?: AbortSignal,
): Promise<MetricsResponse> {
  const end = new Date();
  end.setUTCSeconds(0, 0);
  const start = new Date(end.getTime() - hours * 3_600_000);
  const params = new URLSearchParams({
    start: start.toISOString(),
    end: end.toISOString(),
    interval: hours <= 24 ? 'hour' : 'day',
    currency,
  });
  const data = await apiGet<MetricsResponse>(`/metrics?${params}`, signal);
  if (
    !data ||
    !isSummary(data.overall) ||
    !['hour', 'day'].includes(data.interval) ||
    data.currency !== currency ||
    !Number.isFinite(Date.parse(data.start)) ||
    !Number.isFinite(Date.parse(data.end)) ||
    ![data.by_country, data.by_payment_method, data.time_series].every(
      (items) => Array.isArray(items) && items.every(isSummary),
    ) ||
    !data.time_series.every((item) => Number.isFinite(Date.parse(item.label)))
  )
    throw new ApiError(
      'The API returned an unexpected metrics response. Please try again.',
    );
  return data;
}
