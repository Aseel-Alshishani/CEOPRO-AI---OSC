"""
CEOPRO AI - Ingestion Pipeline Consumer.
Consumes raw market intelligence events and records pipeline execution in the audit log.
"""

import logging
import os
import time
from typing import Optional
import redis
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_AI_CONSUMER_CORE")


class AIStreamConsumer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, group_id: str = "ceopro-ai-nlp-extractors"):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.group_id = group_id
        self.stream_key = "market.intelligence.raw"
        self.consumer_name = f"ai-core-node-{os.getpid()}"

        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")

        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="0", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"Stream consumer online. Group={self.group_id} Worker={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Initialization failure: {str(e)}")
            raise e

    def _write_ingestion_audit_log(self, conn, tenant_id: str, product_name: str, price: float) -> None:
        """
        Records that a raw market record was ingested. This is a pipeline execution
        record, not a verified business fact, so it belongs in audit_logs rather
        than evidence_records.
        """
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_logs (tenant_id, action, entity_type, details)
                VALUES (%s, 'market_record_ingested', 'competitor_price', %s::jsonb);
                """,
                (tenant_id, f'{{"product_name": "{product_name}", "price": {price}}}'),
            )

    def execute_pipeline_listener(self):
        logger.info(f"Listening on stream {self.stream_key}")
        db_connection = None
        try:
            db_connection = psycopg2.connect(self.db_url)
            db_connection.autocommit = False

            while True:
                response = self.client.xreadgroup(
                    groupname=self.group_id,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=10,
                    block=1500
                )

                if not response:
                    continue

                for stream, messages in response:
                    for message_id, payload in messages:
                        try:
                            tenant_id = payload.get("tenant_id")
                            product_name = payload.get("product_name_captured", "unknown")
                            price_found = float(payload.get("price_found", 0.0))

                            self._write_ingestion_audit_log(db_connection, tenant_id, product_name, price_found)

                            db_connection.commit()
                            self.client.xack(self.stream_key, self.group_id, message_id)
                            logger.info(f"Message {message_id} processed and acknowledged.")

                        except Exception as inner_process_err:
                            if db_connection:
                                db_connection.rollback()
                            logger.error(f"Failed to process message {message_id}: {str(inner_process_err)}")
                            continue

                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Shutdown signal received.")
        except Exception as critical_runtime_error:
            logger.critical(f"Fatal error in stream processor: {str(critical_runtime_error)}")
        finally:
            if db_connection:
                db_connection.close()
            self.client.close()
