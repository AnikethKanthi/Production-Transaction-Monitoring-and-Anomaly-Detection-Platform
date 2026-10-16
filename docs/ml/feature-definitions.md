# Transaction feature definitions

The active feature set is `transaction_features.v1`. Feature computation uses transactions
for the same account whose event time is no later than the current transaction. Historical
records are sorted by event time and transaction ID, so database return order cannot change
the result. Monetary baselines use only records with the current transaction's currency.

| Feature | v1 definition |
| --- | --- |
| `transaction_amount` | Current transaction amount. |
| `amount_difference_from_customer_average` | Current amount minus the customer's historical average in the same currency. |
| `transactions_last_5_minutes` | Historical transactions in the trailing five-minute window plus the current transaction. |
| `transactions_last_hour` | Historical transactions in the trailing one-hour window plus the current transaction. |
| `decline_ratio` | Historical failed transactions divided by all historical transactions. |
| `country_change` | `1` when the most recent historical country differs, otherwise `0`. |
| `new_device_indicator` | `1` when a supplied device has not appeared in account history. |
| `new_ip_address_indicator` | `1` when a supplied IP address has not appeared in account history. |
| `unusual_transaction_time` | `1` for event-local hours before 06:00 or from 23:00 onward. |
| `payment_method_frequency` | Share of historical transactions using the current payment method. |
| `order_amount_deviation` | Current order amount minus the historical same-currency order average. |

When history is absent, differences, deviations, ratios, and change indicators are zero;
velocity counts are one because they include the current transaction. A missing order amount
uses the transaction amount. Missing device, IP address, or payment method values produce a
neutral zero signal. Decimal calculations use round-half-even to six decimal places before
conversion to model-ready numbers.

Every accepted event stores the version and feature object in `inference_features`. The
transaction/version uniqueness constraint prevents multiple stored vectors for one definition.
