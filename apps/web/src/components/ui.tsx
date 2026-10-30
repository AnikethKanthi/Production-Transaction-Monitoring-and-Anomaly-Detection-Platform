import type { ReactNode } from 'react';
import { ApiError } from '../api/client';
export const number = (value: number) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
export const percent = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(value);
export const money = (value: number, currency: string) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(value);
export function PageHeading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">TRANSACTION INTELLIGENCE</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {children}
    </section>
  );
}
export function KpiCard({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: string;
  note: string;
  accent?: boolean;
}) {
  return (
    <article className={`kpi ${accent ? 'accent' : ''}`}>
      <span className="kpi-label">{label}</span>
      <strong>{value}</strong>
      <span className="kpi-note">{note}</span>
    </article>
  );
}
export function EmptyState({
  title = 'No transactions in this period',
  description = 'Choose another time range or currency. New transactions will appear as they are processed.',
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty-state" role="status">
      <span aria-hidden="true">○</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>Couldn’t load live data</strong>
        <p>{error.message}</p>
        {error instanceof ApiError && error.correlationId && (
          <small>Reference: {error.correlationId}</small>
        )}
      </div>
      <button onClick={retry}>Try again</button>
    </div>
  );
}
export function LoadingState() {
  return (
    <div className="loading-state" role="status" aria-label="Loading live data">
      <div className="skeleton-kpis">
        {[1, 2, 3, 4].map((key) => (
          <div className="skeleton" key={key} />
        ))}
      </div>
      <div className="skeleton skeleton-chart" />
      <span>Loading live data…</span>
    </div>
  );
}
export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className={`badge ${String(children)}`}>
      {String(children).replaceAll('_', ' ')}
    </span>
  );
}
