import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../api/client';
import type { Transaction, Page } from '../api/investigations';
import { utc } from '../api/investigations';
import { Pagination, useListFilters } from '../components/list-controls';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  Panel,
  money,
} from '../components/ui';

export default function TransactionsPage() {
  const filters = useListFilters([
    'search',
    'status',
    'country',
    'currency',
    'min_amount',
    'max_amount',
    'occurred_from',
    'occurred_to',
    'sort_by',
    'sort_order',
  ]);
  const { params } = filters;
  const query = useQuery({
    queryKey: ['transactions', filters.query],
    queryFn: ({ signal }) =>
      apiGet<Page<Transaction>>(`/transactions?${filters.query}`, signal),
  });
  const sort = params.get('sort_by') || 'occurred_at';
  const direction = params.get('sort_order') || 'desc';
  const sortButton = (key: string, label: string) => (
    <th
      scope="col"
      aria-sort={
        sort === key
          ? direction === 'asc'
            ? 'ascending'
            : 'descending'
          : 'none'
      }
    >
      <button
        className="sort-button"
        onClick={() =>
          filters.update({
            sort_by: key,
            sort_order: sort === key && direction === 'desc' ? 'asc' : 'desc',
          })
        }
      >
        {label} {sort === key ? (direction === 'asc' ? '↑' : '↓') : '↕'}
      </button>
    </th>
  );
  return (
    <>
      <PageHeading
        title="Transactions"
        description="Search accounts, merchants, or a full transaction ID. Investigate scores and related alerts."
      />
      <form
        key={params.toString()}
        className="filter-form"
        onSubmit={filters.submit}
        aria-label="Transaction filters"
      >
        <label className="search-field">
          Search transactions
          <input
            name="search"
            type="search"
            maxLength={128}
            defaultValue={params.get('search') || ''}
            placeholder="Account, merchant, or full transaction ID"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={params.get('status') || ''}>
            <option value="">All statuses</option>
            {['pending', 'completed', 'failed', 'refunded'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Country
          <input
            name="country"
            maxLength={2}
            pattern="[A-Za-z]{2}"
            placeholder="US"
            defaultValue={params.get('country') || ''}
          />
        </label>
        <label>
          Currency
          <select name="currency" defaultValue={params.get('currency') || ''}>
            <option value="">All currencies</option>
            {['USD', 'GBP', 'EUR', 'CAD'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Minimum amount
          <input
            name="min_amount"
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={params.get('min_amount') || ''}
          />
        </label>
        <label>
          Maximum amount
          <input
            name="max_amount"
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={params.get('max_amount') || ''}
          />
        </label>
        <label>
          From date (UTC)
          <input
            name="occurred_from"
            type="date"
            defaultValue={params.get('occurred_from')?.slice(0, 10) || ''}
          />
        </label>
        <label>
          To date (UTC)
          <input
            name="occurred_to"
            type="date"
            defaultValue={params.get('occurred_to')?.slice(0, 10) || ''}
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
          title="Transaction ledger"
          subtitle={`${query.data.pagination.total} transactions`}
        >
          {query.data.items.length ? (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">
                  Transactions matching your filters. Select an ID to
                  investigate.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Transaction</th>
                    <th scope="col">Account</th>
                    {sortButton('amount', 'Amount')}
                    {sortButton('country', 'Country')}
                    {sortButton('status', 'Status')}
                    {sortButton('occurred_at', 'Time (UTC)')}
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link
                          className="record-link mono"
                          to={`/transactions/${row.id}?${params}`}
                          aria-label={`Investigate transaction ${row.id}`}
                        >
                          {row.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td>{row.account_id}</td>
                      <td>
                        {money(Number(row.amount), row.currency)}{' '}
                        <small>{row.currency}</small>
                      </td>
                      <td>{row.country}</td>
                      <td>
                        <Badge>{row.status}</Badge>
                      </td>
                      <td>{utc(row.occurred_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No transactions found"
              description="Change or clear the filters to find other transactions."
            />
          )}
          <Pagination total={query.data.pagination.total} {...filters} />
        </Panel>
      )}
    </>
  );
}
