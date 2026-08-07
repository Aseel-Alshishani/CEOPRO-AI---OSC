"""
Tests ForecastRequestConsumer against a real Redis instance - constructing it
requires an actual reachable Redis (xgroup_create is called eagerly in
__init__, and a ConnectionError there isn't caught), so this can't be a pure
mock-based unit test the way test_pipeline.py's DB tests are.

Skipped automatically unless AI_TEST_REDIS_HOST is set, so it never runs in CI
or requires Docker on every machine. Point it at a disposable Redis - tests
create/use a real consumer group on ceopro:stream:forecast_requested.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.ai.forecasting.consumer import ForecastRequestConsumer

REDIS_HOST = os.getenv("AI_TEST_REDIS_HOST")
REDIS_PORT = int(os.getenv("AI_TEST_REDIS_PORT", "6379"))

pytestmark = pytest.mark.skipif(not REDIS_HOST, reason="AI_TEST_REDIS_HOST not set - skipping live-Redis consumer test")


@pytest.fixture(autouse=True)
def dummy_database_url(monkeypatch):
    # __init__ only checks DATABASE_URL is set, it doesn't connect - the tests
    # here mock out pipeline.run_forecast so no real DB is needed.
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused:unused@localhost/unused")


@pytest.fixture
def redis_client():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def consumer(redis_client):
    return ForecastRequestConsumer(host=REDIS_HOST, port=REDIS_PORT)


def test_init_creates_consumer_group_on_stream(consumer, redis_client):
    groups = redis_client.xinfo_groups(consumer.stream_key)
    assert any(g["name"] == consumer.group_id for g in groups)


def test_handle_message_raises_on_missing_tenant_id(consumer):
    with pytest.raises(ValueError, match="Malformed"):
        consumer._handle_message(db_connection=None, payload={"product_id": "p1", "horizon_days": "7"})


def test_handle_message_raises_on_missing_product_id(consumer):
    with pytest.raises(ValueError, match="Malformed"):
        consumer._handle_message(db_connection=None, payload={"tenant_id": "t1", "horizon_days": "7"})


def test_handle_message_calls_run_forecast_with_parsed_args(consumer):
    with patch("src.ai.forecasting.consumer.run_forecast") as mock_run_forecast:
        consumer._handle_message(
            db_connection="fake-conn", payload={"tenant_id": "t1", "product_id": "p1", "horizon_days": "14"}
        )
    mock_run_forecast.assert_called_once_with("fake-conn", "t1", "p1", 14)


def test_handle_message_defaults_horizon_days_to_seven(consumer):
    with patch("src.ai.forecasting.consumer.run_forecast") as mock_run_forecast:
        consumer._handle_message(db_connection="fake-conn", payload={"tenant_id": "t1", "product_id": "p1"})
    mock_run_forecast.assert_called_once_with("fake-conn", "t1", "p1", 7)


def test_full_publish_consume_ack_cycle_matches_listen_loop_mechanics(consumer, redis_client):
    """
    Exercises the same xreadgroup -> handle -> xack sequence listen() uses,
    without invoking listen()'s infinite loop.
    """
    redis_client.xadd(consumer.stream_key, {"tenant_id": "t1", "product_id": "p1", "horizon_days": "7"})

    with patch("src.ai.forecasting.consumer.run_forecast") as mock_run_forecast:
        response = consumer.client.xreadgroup(
            groupname=consumer.group_id, consumername=consumer.consumer_name,
            streams={consumer.stream_key: ">"}, count=10, block=1000,
        )
        assert response, "expected the published message to be delivered"

        for _stream, messages in response:
            for message_id, payload in messages:
                consumer._handle_message("fake-conn", payload)
                consumer.client.xack(consumer.stream_key, consumer.group_id, message_id)

    mock_run_forecast.assert_called_once_with("fake-conn", "t1", "p1", 7)

    pending = redis_client.xpending(consumer.stream_key, consumer.group_id)
    assert pending["pending"] == 0  # message was acked, nothing left outstanding


def test_listen_closes_db_and_redis_on_keyboard_interrupt(consumer):
    """
    listen()'s own while-loop, KeyboardInterrupt handling, and finally-block
    cleanup - previously untested (only the per-message logic it calls was
    covered). xreadgroup raising KeyboardInterrupt simulates Ctrl+C landing
    during the blocking read.
    """
    fake_db_conn = MagicMock()
    consumer.client.xreadgroup = MagicMock(side_effect=KeyboardInterrupt)

    with patch("src.ai.forecasting.consumer.psycopg2.connect", return_value=fake_db_conn):
        consumer.listen()  # must not raise - KeyboardInterrupt is caught internally

    fake_db_conn.close.assert_called_once()


def test_listen_continues_past_empty_responses(consumer):
    """An empty xreadgroup response (timeout, no messages) must not stop the loop."""
    fake_db_conn = MagicMock()
    consumer.client.xreadgroup = MagicMock(side_effect=[[], [], KeyboardInterrupt])

    with patch("src.ai.forecasting.consumer.psycopg2.connect", return_value=fake_db_conn):
        consumer.listen()

    assert consumer.client.xreadgroup.call_count == 3
    fake_db_conn.close.assert_called_once()


def test_listen_rolls_back_and_continues_on_message_processing_error(consumer):
    """A malformed message must not crash the loop - it should roll back and move on."""
    fake_db_conn = MagicMock()
    malformed_response = [(consumer.stream_key, [("123-0", {"product_id": "p1"})])]  # missing tenant_id
    consumer.client.xreadgroup = MagicMock(side_effect=[malformed_response, KeyboardInterrupt])
    consumer.client.xack = MagicMock()

    with patch("src.ai.forecasting.consumer.psycopg2.connect", return_value=fake_db_conn):
        consumer.listen()

    fake_db_conn.rollback.assert_called_once()
    consumer.client.xack.assert_not_called()  # a message that raised must not be acked
    fake_db_conn.close.assert_called_once()


def test_listen_acks_only_after_successful_processing(consumer):
    fake_db_conn = MagicMock()
    good_response = [(consumer.stream_key, [("124-0", {"tenant_id": "t1", "product_id": "p1"})])]
    consumer.client.xreadgroup = MagicMock(side_effect=[good_response, KeyboardInterrupt])
    consumer.client.xack = MagicMock()

    with patch("src.ai.forecasting.consumer.psycopg2.connect", return_value=fake_db_conn), \
         patch("src.ai.forecasting.consumer.run_forecast") as mock_run_forecast:
        consumer.listen()

    mock_run_forecast.assert_called_once_with(fake_db_conn, "t1", "p1", 7)
    consumer.client.xack.assert_called_once_with(consumer.stream_key, consumer.group_id, "124-0")
    fake_db_conn.rollback.assert_not_called()
