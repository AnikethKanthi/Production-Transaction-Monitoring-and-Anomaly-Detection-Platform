import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../api/client';
import type { Investigation } from '../api/investigations';
import { utc } from '../api/investigations';
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  Panel,
  money,
} from '../components/ui';

export default function TransactionDetailsPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const query = useQuery({
    queryKey: ['transaction', id],
    queryFn: ({ signal }) =>
      apiGet<Investigation>(`/transactions/${id}/investigation`, signal),
  });
  const data = query.data;
  return (
    <>
      <Link className="back-link" to={`/transactions?${params}`}>
        ← Back to filtered transactions
      </Link>
      <PageHeading
        title="Transaction investigation"
        description="Inspect the payment, model result, and related alerts."
      />
      {query.isPending && <LoadingState />}
      {query.isError && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {data && (
        <>
          <Panel title="Transaction details">
            <dl className="detail-grid">
              {Object.entries({
                'Transaction ID': data.transaction.id,
                Account: data.transaction.account_id,
                Merchant: data.transaction.merchant_id || 'Not supplied',
                Amount: money(
                  Number(data.transaction.amount),
                  data.transaction.currency,
                ),
                Currency: data.transaction.currency,
                Country: data.transaction.country,
                Status: data.transaction.status,
                'Payment method':
                  data.transaction.payment_method || 'Not supplied',
                Device: data.transaction.device_id || 'Not supplied',
                'IP address': data.transaction.ip_address || 'Not supplied',
                Occurred: utc(data.transaction.occurred_at),
              }).map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <div className="investigation-grid">
            <Panel title="Model assessment">
              {data.anomaly ? (
                <>
                  <p className="score-value">{data.anomaly.score.toFixed(6)}</p>
                  <dl className="detail-grid">
                    <div>
                      <dt>Model version</dt>
                      <dd>{data.anomaly.model_version}</dd>
                    </div>
                    <div>
                      <dt>Scoring status</dt>
                      <dd>
                        <Badge>{data.anomaly.scoring_status}</Badge>
                      </dd>
                    </div>
                    <div>
                      <dt>Inference latency</dt>
                      <dd>
                        {(
                          data.anomaly.inference_latency_seconds * 1000
                        ).toFixed(2)}{' '}
                        ms
                      </dd>
                    </div>
                  </dl>
                  {data.anomaly.scoring_status === 'fallback' && (
                    <p role="status">
                      Fallback score: the model was unavailable. This is not a
                      model risk assessment.
                    </p>
                  )}
                </>
              ) : (
                <EmptyState
                  title="Not scored yet"
                  description="API-created transactions may not have been processed by the scoring worker."
                />
              )}
            </Panel>
            <Panel title="Related alerts">
              {data.alerts.length ? (
                data.alerts.map((alert) => (
                  <article className="alert-row" key={alert.id}>
                    <Link
                      className="record-link"
                      to={`/alerts/${alert.id}?transaction_id=${data.transaction.id}`}
                    >
                      Investigate alert {alert.id.slice(0, 8)}
                    </Link>
                    <p>
                      <Badge>{alert.severity}</Badge>{' '}
                      <Badge>{alert.status}</Badge>
                    </p>
                    <p>
                      {alert.evidence.reasons?.join(' ') ||
                        'Review model evidence in the alert.'}
                    </p>
                  </article>
                ))
              ) : (
                <EmptyState
                  title="No related alerts"
                  description="No alert policy has created an alert for this transaction."
                />
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
