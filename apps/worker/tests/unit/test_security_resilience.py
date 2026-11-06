import json
import logging
import sys
from threading import Event
from unittest.mock import Mock

import numpy as np
import pytest
from confluent_kafka import KafkaError, KafkaException
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import InterfaceError, OperationalError
from test_anomaly_processor import features
from test_transaction_consumer import event_payload, message

from worker.consumers.transaction_consumer import TransactionConsumer
from worker.events.transaction import deserialize_transaction_event
from worker.logging import JsonFormatter
from worker.monitoring.metrics import WORKER_EVENTS
from worker.monitoring.rolling_metrics import RollingMetricsCounter
from worker.processors.anomaly_processor import AnomalyProcessor, ScoreResult


@pytest.mark.parametrize("invalidated", [False, True])
def test_postgres_failure_has_bounded_jitter_and_leaves_offset_uncommitted(invalidated):
    client, publisher, sleeper = Mock(), Mock(), Mock()
    failure = InterfaceError if invalidated else OperationalError
    processor = Mock(
        side_effect=failure(
            "secret SQL",
            {"pan": "4111111111111111"},
            Exception("password=private"),
            connection_invalidated=invalidated,
        )
    )
    with pytest.raises(failure):
        TransactionConsumer(
            client,
            processor,
            publisher,
            max_processing_attempts=3,
            retry_backoff_seconds=60,
            random_source=lambda: 0.5,
            sleeper=sleeper,
        )._handle(message(event_payload()))
    assert processor.call_count == 3
    assert [call.args[0] for call in sleeper.call_args_list] == [15, 15]
    publisher.assert_not_called()
    client.commit.assert_not_called()


def test_kafka_poll_outage_recovers_and_shutdown_closes_consumer():
    stop = Event()
    client = Mock()

    def end(_timeout):
        stop.set()
        return None

    client.poll.side_effect = [KafkaException(KafkaError(KafkaError._TRANSPORT)), None]
    count = 0

    def poll(timeout):
        nonlocal count
        count += 1
        if count == 1:
            raise KafkaException(KafkaError(KafkaError._TRANSPORT))
        return end(timeout)

    client.poll.side_effect = poll
    TransactionConsumer(client, Mock(), Mock(), random_source=lambda: 0).run(stop)
    assert count == 2
    client.close.assert_called_once()
    client.commit.assert_not_called()


def test_kafka_commit_failure_never_counts_success():
    client = Mock()
    client.commit.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
    before = WORKER_EVENTS.labels("processed")._value.get()
    with pytest.raises(KafkaException):
        TransactionConsumer(client, Mock(), Mock())._handle(message(event_payload()))
    assert WORKER_EVENTS.labels("processed")._value.get() == before


def test_fatal_kafka_poll_error_exits_and_closes_for_supervised_restart():
    client = Mock()
    fatal = Mock(spec=KafkaError)
    fatal.fatal.return_value = True
    client.poll.side_effect = KafkaException(fatal)
    with pytest.raises(KafkaException):
        TransactionConsumer(client, Mock(), Mock()).run(Event())
    client.close.assert_called_once()


def test_redis_outage_is_optional_for_worker_and_logs_no_exception_payload():
    redis = Mock()
    redis.pipeline.side_effect = RedisConnectionError("password=private 4111111111111111")
    transaction = deserialize_transaction_event(event_payload()).data
    RollingMetricsCounter(redis, 60).record(
        transaction, ScoreResult(0, "fallback.v1", "fallback", None, 0)
    )


@pytest.mark.parametrize("invalid", [False, True])
def test_model_faults_return_safe_fallback(invalid):
    model = Mock()
    if invalid:
        model.decision_function.return_value = np.asarray([np.nan])
    else:
        model.decision_function.side_effect = RuntimeError(
            "secret=private card_number=4111111111111111"
        )
    score = AnomalyProcessor(model, "model.v1").score(features())
    assert score.status == "fallback" and score.model_version == "fallback.v1"
    assert score.score == 0
    assert "private" not in score.failure_reason
    assert "4111111111111111" not in score.failure_reason


def test_worker_json_logs_remove_payment_and_exception_secrets(monkeypatch):
    monkeypatch.setenv("TEST_PASSWORD", "environment-secret")
    try:
        raise RuntimeError("arbitrary-payment-payload 4111111111111111 cvv=123")
    except RuntimeError:
        record = logging.LogRecord(
            "worker.test",
            logging.ERROR,
            __file__,
            1,
            "4111 1111 1111 1111 card_number=4111111111111111 cvv=123 "
            "Bearer opaque-secret redis://user:password@host environment-secret",
            (),
            sys.exc_info(),
        )
    value = JsonFormatter().format(record)
    for sensitive in (
        "4111",
        "123",
        "opaque-secret",
        "password@",
        "environment-secret",
        "arbitrary-payment-payload",
    ):
        assert sensitive not in value
    assert json.loads(value)["exception"] == "RuntimeError"
