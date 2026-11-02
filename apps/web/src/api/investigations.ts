export interface Transaction {
  id: string;
  account_id: string;
  merchant_id: string | null;
  amount: string;
  currency: string;
  country: string;
  status: string;
  occurred_at: string;
  device_id: string | null;
  ip_address: string | null;
  payment_method: string | null;
  order_amount: string | null;
}
export interface Alert {
  id: string;
  transaction_id: string;
  severity: string;
  status: string;
  assignee: string | null;
  version: number;
  model_version: string;
  policy_version: string;
  evidence: {
    reasons?: string[];
    score?: number;
    threshold?: number;
    observed_features?: Record<string, unknown>;
  };
  created_at: string;
}
export interface AuditEntry {
  id: string;
  version: number;
  action: string;
  actor: string;
  reason: string;
  before: { status: string; assignee: string | null } | null;
  after: { status: string; assignee: string | null };
  created_at: string;
}
export interface AlertDetails extends Alert {
  audit_history: AuditEntry[];
}
export interface Investigation {
  transaction: Transaction;
  anomaly: {
    score: number;
    model_version: string;
    scoring_status: string;
    failure_reason: string | null;
    inference_latency_seconds: number;
  } | null;
  alerts: Alert[];
}
export interface Page<T> {
  items: T[];
  pagination: { total: number; limit: number; offset: number };
}
export const utc = (value: string) =>
  `${new Date(value).toLocaleString('en-US', { timeZone: 'UTC' })} UTC`;
