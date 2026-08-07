"""
CEOPRO AI - Demand Forecast Request Consumer.
Consumes the `demand_forecast_requested` event contract (see
src/infrastructure/DATA_OWNERSHIP_AND_CONTRACTS.md, Event B) from the
`ceopro:stream:forecast_requested` topic already provisioned by
src/infrastructure/init_broker.py, and runs the forecasting pipeline.

This is a separate consumer from src/infrastructure/messaging/ai_consumer.py,
which handles the unrelated market-intelligence-raw stream; that file's
ownership is a separate, still-open question (see AI_PLAN_AND_CONTRACT_UPDATES.md)
and is not touched here.
"""

import logging
import os
import time
from typing import Optional

import psycopg2
import redis

from src.ai.forecasting.pipeline import run_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_AI_FORECAST_CONSUMER")


class ForecastRequestConsumer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.group_id = "ceopro-ai-forecast-engine"
        self.stream_key = "ceopro:stream:forecast_requested"
        self.consumer_name = f"ai-forecast-node-{os.getpid()}"

        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")

        self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
        try:
            self.client.xgroup_create(self.stream_key, self.group_id, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass
        logger.info(f"Forecast consumer online. Group={self.group_id} Worker={self.consumer_name}")

    def _handle_message(self, db_connection, payload: dict) -> None:
        tenant_id = payload.get("tenant_id")
        product_id = payload.get("product_id")
        horizon_days = int(payload.get("horizon_days", 7))

        if not tenant_id or not product_id:
            raise ValueError(f"Malformed demand_forecast_requested payload: {payload}")

        run_forecast(db_connection, tenant_id, product_id, horizon_days)

    def listen(self) -> None:
        logger.info(f"Listening on stream {self.stream_key}")
        db_connection = psycopg2.connect(self.db_url)
        db_connection.autocommit = False

        try:
            while True:
                response = self.client.xreadgroup(
                    groupname=self.group_id,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=10,
                    block=1500,
                )

                if not response:
                    continue

                for _stream, messages in response:
                    for message_id, message_payload in messages:
                        try:
                            self._handle_message(db_connection, message_payload)
                            self.client.xack(self.stream_key, self.group_id, message_id)
                            logger.info(f"Message {message_id} processed and acknowledged.")
                        except Exception as inner_process_err:
                            db_connection.rollback()
                            logger.error(f"Failed to process message {message_id}: {str(inner_process_err)}")
                            continue

                time.sleep(0.01)
        except KeyboardInterrupt:
            logger.info("Shutdown signal received.")
        finally:
            db_connection.close()
            self.client.close()


if __name__ == "__main__":
    ForecastRequestConsumer().listen()
