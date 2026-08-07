import logging
import os
import time
import json
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

        self.db_url = self._resolve_db_url()
        
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

    def _resolve_db_url(self) -> str:
        url = os.getenv("DATABASE_URL")
        if not url:
            user = os.getenv("POSTGRES_USER", "ceopro_admin")
            pwd = os.getenv("POSTGRES_PASSWORD", "SecurePassword2026")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "ceopro_platform")
            url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
        return url

    def _write_ingestion_staging_record(self, conn, tenant_id: str, product_name: str, price: float, currency: str) -> None:
        raw_payload = {
            "product_name_captured": product_name,
            "price_found": price,
            "currency": currency,
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO import_staging_rows (job_id, tenant_id, row_number, raw_data, validation_status)
                VALUES (
                    '00000000-0000-0000-0000-000000000000'::uuid, 
                    %s::uuid, 
                    1, 
                    %s::jsonb, 
                    'needs_review'
                );
                """,
                (tenant_id, json.dumps(raw_payload)),
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
                            currency = payload.get("currency", "JOD")

                            self._write_ingestion_staging_record(db_connection, tenant_id, product_name, price_found, currency)

                            db_connection.commit()
                            self.client.xack(self.stream_key, self.group_id, message_id)
                            logger.info(f"Message {message_id} processed and staged successfully.")

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
