import { useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../api/client';
import type { AlertDetails, Alert } from '../api/investigations';
import { utc } from '../api/investigations';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  Panel,
} from '../components/ui';

export default function AlertDetailsPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['alert', id],
    queryFn: ({ signal }) => apiGet<AlertDetails>(`/alerts/${id}`, signal),
  });
  const [action, setAction] = useState('assign');
  const [notice, setNotice] = useState('');
  const noticeRef = useRef<HTMLDivElement>(null);
  const mutation = useMutation({
    mutationFn: ({
      operation,
      body,
    }: {
      operation: string;
      body: Record<string, unknown>;
    }) => apiPost<Alert>(`/alerts/${id}/${operation}`, body),
    retry: false,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['alert', id] }),
        client.invalidateQueries({ queryKey: ['alerts'] }),
        client.invalidateQueries({ queryKey: ['transaction'] }),
      ]);
      setNotice('Alert updated. Latest details and audit history loaded.');
      window.setTimeout(() => noticeRef.current?.focus(), 0);
    },
  });
  const data = query.data;
  const closed = data && ['resolved', 'false_positive'].includes(data.status);
  return (
    <>
      <Link className="back-link" to={`/alerts?${params}`}>
        ← Back to filtered alerts
      </Link>
      <PageHeading
        title="Alert investigation"
        description="Review the evidence, document your decision, and update the alert."
      />
      <div
        role="status"
        ref={noticeRef}
        tabIndex={-1}
        className={notice ? 'success-notice' : ''}
      >
        {notice}
      </div>
      {query.isPending && <LoadingState />}
      {query.isError && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {data && (
        <>
          <Panel title="Alert details">
            <div className="alert-title">
              <Badge>{data.severity}</Badge>
              <Badge>{data.status}</Badge>
              <span>Version {data.version}</span>
            </div>
            <dl className="detail-grid">
              <div>
                <dt>Alert ID</dt>
                <dd>{data.id}</dd>
              </div>
              <div>
                <dt>Transaction</dt>
                <dd>
                  <Link
                    className="record-link"
                    to={`/transactions/${data.transaction_id}`}
                  >
                    {data.transaction_id}
                  </Link>
                </dd>
              </div>
              <div>
                <dt>Assigned to</dt>
                <dd>{data.assignee || 'Unassigned'}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{data.model_version}</dd>
              </div>
              <div>
                <dt>Policy</dt>
                <dd>{data.policy_version}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{utc(data.created_at)}</dd>
              </div>
            </dl>
          </Panel>
          <div className="investigation-grid">
            <Panel title="Anomaly evidence">
              <dl className="detail-grid">
                <div>
                  <dt>Anomaly score</dt>
                  <dd className="score-value">
                    {typeof data.evidence.score === 'number'
                      ? data.evidence.score.toFixed(6)
                      : 'Unavailable'}
                  </dd>
                </div>
                <div>
                  <dt>Alert threshold</dt>
                  <dd>
                    {typeof data.evidence.threshold === 'number'
                      ? data.evidence.threshold.toFixed(6)
                      : 'Unavailable'}
                  </dd>
                </div>
              </dl>
              <h3>Reasons</h3>
              <ul className="reasons">
                {(
                  data.evidence.reasons || [
                    'No reasons were supplied with this alert.',
                  ]
                ).map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
              <details>
                <summary>Observed inference features</summary>
                <dl className="detail-grid">
                  {Object.entries(data.evidence.observed_features || {}).map(
                    ([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll('_', ' ')}</dt>
                        <dd>{JSON.stringify(value)}</dd>
                      </div>
                    ),
                  )}
                </dl>
                <p>Observed context, not a causal explanation of the model.</p>
              </details>
            </Panel>
            <Panel title="Investigation actions">
              {closed ? (
                <p role="status">
                  This alert is closed. Its evidence and audit history remain
                  available.
                </p>
              ) : (
                <form
                  className="action-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (mutation.isPending || query.isFetching) return;
                    const fields = new FormData(event.currentTarget);
                    setNotice('');
                    mutation.mutate({
                      operation: action,
                      body: {
                        expected_version: data.version,
                        actor: String(fields.get('actor')).trim(),
                        reason: String(fields.get('reason')).trim(),
                        ...(action === 'assign'
                          ? { assignee: String(fields.get('assignee')).trim() }
                          : {}),
                      },
                    });
                  }}
                >
                  <label>
                    Action
                    <select
                      value={action}
                      onChange={(event) => {
                        setAction(event.target.value);
                        mutation.reset();
                      }}
                      disabled={mutation.isPending}
                    >
                      <option
                        value="acknowledge"
                        disabled={data.status !== 'open'}
                      >
                        Acknowledge
                      </option>
                      <option value="assign">Assign / reassign</option>
                      <option value="resolve">Resolve</option>
                      <option value="false-positive">
                        Mark as false positive
                      </option>
                    </select>
                  </label>
                  <label>
                    Your operator ID
                    <input
                      name="actor"
                      required
                      maxLength={128}
                      pattern=".*\S.*"
                      autoComplete="username"
                    />
                  </label>
                  {action === 'assign' && (
                    <label>
                      Assign to
                      <input
                        name="assignee"
                        required
                        maxLength={128}
                        pattern=".*\S.*"
                      />
                    </label>
                  )}
                  <label>
                    Investigation note
                    <textarea
                      name="reason"
                      required
                      maxLength={2000}
                      rows={4}
                    />
                  </label>
                  <p className="chart-note">
                    Your operator ID and note are recorded in the audit history.
                  </p>
                  <button disabled={mutation.isPending || query.isFetching}>
                    {mutation.isPending ? 'Saving…' : 'Apply action'}
                  </button>
                </form>
              )}
              {mutation.isError && (
                <div role="alert" className="error-state">
                  <div>
                    <strong>Action was not confirmed</strong>
                    <p>{mutation.error.message}</p>
                    <p>
                      Reload before retrying: an interrupted request may already
                      have been applied.
                    </p>
                    <button
                      onClick={() => {
                        void query.refetch();
                        mutation.reset();
                      }}
                    >
                      Reload latest alert
                    </button>
                  </div>
                </div>
              )}
            </Panel>
          </div>
          <Panel title="Audit history" subtitle="Ordered by alert version">
            <ol className="audit-list">
              {data.audit_history.map((entry) => (
                <li key={entry.id}>
                  <strong>
                    Version {entry.version} ·{' '}
                    {entry.action.replaceAll('-', ' ')}
                  </strong>
                  <span>
                    {utc(entry.created_at)} · {entry.actor}
                  </span>
                  <p>{entry.reason}</p>
                  <small>
                    {entry.before
                      ? `${entry.before.status} → ${entry.after.status}`
                      : `Created as ${entry.after.status}`}{' '}
                    · Assignee: {entry.after.assignee || 'Unassigned'}
                  </small>
                </li>
              ))}
            </ol>
          </Panel>
        </>
      )}
    </>
  );
}
