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
  money,
} from '../components/ui';
type Transaction = {
  id: string;
  account_id: string;
  amount: string;
  currency: string;
  country: string;
  status: string;
  occurred_at: string;
};
export default function TransactionsPage() {
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ['transactions', offset],
    queryFn: ({ signal }) =>
      apiGet<{ items: Transaction[]; pagination: { total: number } }>(
        `/transactions?limit=20&offset=${offset}`,
        signal,
      ),
  });
  return (
    <>
      <PageHeading
        title="Transactions"
        description="Explore your most recent payment activity."
      />
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
                <thead>
                  <tr>
                    <th>Transaction</th>
                    <th>Account</th>
                    <th>Amount</th>
                    <th>Country</th>
                    <th>Status</th>
                    <th>Time (UTC)</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((row) => (
                    <tr key={row.id}>
                      <td className="mono" title={row.id}>
                        {row.id.slice(0, 8)}
                      </td>
                      <td>{row.account_id}</td>
                      <td>{money(Number(row.amount), row.currency)}</td>
                      <td>{row.country}</td>
                      <td>
                        <Badge>{row.status}</Badge>
                      </td>
                      <td>
                        {new Date(row.occurred_at).toLocaleString('en-US', {
                          timeZone: 'UTC',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No transactions found" />
          )}
          <div className="pagination">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Previous
            </button>
            <span>Page {Math.floor(offset / 20) + 1}</span>
            <button
              disabled={offset + 20 >= query.data.pagination.total}
              onClick={() => setOffset(offset + 20)}
            >
              Next
            </button>
          </div>
        </Panel>
      )}
    </>
  );
}
