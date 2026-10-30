import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../api/client';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  Panel,
} from '../components/ui';
type Alert = {
  id: string;
  transaction_id: string;
  severity: string;
  status: string;
  assignee: string | null;
  evidence: { reasons?: string[] };
  created_at: string;
};
export default function AlertsPage() {
  const [status, setStatus] = useState('');
  const query = useQuery({
    queryKey: ['alerts', status],
    queryFn: ({ signal }) =>
      apiGet<{ items: Alert[]; pagination: { total: number } }>(
        `/alerts?limit=50${status ? `&status=${status}` : ''}`,
        signal,
      ),
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeading
        title="Alerts"
        description="Review suspicious activity and the evidence behind each alert."
      />
      <div className="toolbar">
        <label>
          Status{' '}
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {['open', 'acknowledged', 'resolved', 'false_positive'].map(
              (value) => (
                <option key={value} value={value}>
                  {value.replaceAll('_', ' ')}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      {query.isPending && <LoadingState />}
      {query.isError && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {query.data && (
        <Panel
          title="Alert queue"
          subtitle={`${query.data.pagination.total} alerts · latest 50`}
        >
          {query.data.items.length ? (
            <div className="alert-list">
              {query.data.items.map((row) => (
                <article className="alert-row" key={row.id}>
                  <div className="alert-title">
                    <Badge>{row.severity}</Badge>
                    <Badge>{row.status}</Badge>
                    <span className="mono">
                      {row.transaction_id.slice(0, 8)}
                    </span>
                  </div>
                  <p>
                    {row.evidence.reasons?.join(' ') ||
                      'Anomaly score exceeded the configured alert threshold.'}
                  </p>
                  <small>
                    {row.assignee
                      ? `Assigned to ${row.assignee}`
                      : 'Unassigned'}{' '}
                    ·{' '}
                    {new Date(row.created_at).toLocaleString('en-US', {
                      timeZone: 'UTC',
                    })}{' '}
                    UTC
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No alerts found"
              description="Alerts matching this status will appear here."
            />
          )}
        </Panel>
      )}
    </>
  );
}
