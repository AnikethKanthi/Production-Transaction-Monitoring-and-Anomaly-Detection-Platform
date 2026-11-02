import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../api/client';
import type { Alert, Page } from '../api/investigations';
import { utc } from '../api/investigations';
import { Pagination, useListFilters } from '../components/list-controls';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  Panel,
} from '../components/ui';

export default function AlertsPage() {
  const filters = useListFilters(['status', 'severity', 'transaction_id']);
  const { params } = filters;
  const query = useQuery({
    queryKey: ['alerts', filters.query],
    queryFn: ({ signal }) =>
      apiGet<Page<Alert>>(`/alerts?${filters.query}`, signal),
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeading
        title="Alerts"
        description="Prioritize the queue, inspect evidence, and complete your investigation."
      />
      <form
        key={params.toString()}
        className="filter-form"
        onSubmit={filters.submit}
        aria-label="Alert filters"
      >
        <label>
          Status
          <select name="status" defaultValue={params.get('status') || ''}>
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
        <label>
          Severity
          <select name="severity" defaultValue={params.get('severity') || ''}>
            <option value="">All severities</option>
            {['low', 'medium', 'high', 'critical'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="search-field">
          Transaction ID
          <input
            name="transaction_id"
            defaultValue={params.get('transaction_id') || ''}
            placeholder="Full transaction UUID"
          />
        </label>
        <div className="filter-buttons">
          <button type="submit">Apply filters</button>
          <button type="button" className="secondary" onClick={filters.reset}>
            Clear filters
          </button>
        </div>
      </form>
      {query.isPending && <LoadingState />}
      {query.isError && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {query.data && (
        <Panel
          title="Alert queue"
          subtitle={`${query.data.pagination.total} alerts`}
        >
          {query.data.items.length ? (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Alert investigation queue</caption>
                <thead>
                  <tr>
                    <th scope="col">Alert</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Status</th>
                    <th scope="col">Score</th>
                    <th scope="col">Assigned to</th>
                    <th scope="col">Created (UTC)</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link
                          className="record-link mono"
                          to={`/alerts/${row.id}?${params}`}
                          aria-label={`Investigate alert ${row.id}`}
                        >
                          {row.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td>
                        <Badge>{row.severity}</Badge>
                      </td>
                      <td>
                        <Badge>{row.status}</Badge>
                      </td>
                      <td>
                        {typeof row.evidence.score === 'number'
                          ? row.evidence.score.toFixed(6)
                          : 'Unavailable'}
                      </td>
                      <td>{row.assignee || 'Unassigned'}</td>
                      <td>{utc(row.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No alerts found"
              description="Change or clear filters to review other alerts."
            />
          )}
          <Pagination total={query.data.pagination.total} {...filters} />
        </Panel>
      )}
    </>
  );
}
