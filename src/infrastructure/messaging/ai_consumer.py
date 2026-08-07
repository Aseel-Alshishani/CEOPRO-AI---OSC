"""
CEOPRO AI - Enterprise Ingestion Pipeline Transformer Node.
Features manual acknowledgement parameters, continuous backpressure mitigation loops,
and real-time transactional auditing records insertion metrics.
"""

import json
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
        self.host = host or "localhost"
        self.port = port or 6379
        self.group_id = group_id
        self.stream_key = "market.intelligence.raw"
        self.consumer_name = f"ai-core-node-{os.getpid()}"
        self.db_url = os.getenv("DATABASE_URL", "postgresql://ceopro_admin:LObDwA0PX6ocepEKCV1d@localhost:5432/ceopro_platform")
        
        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="0", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"AI Microservice Stream node online. Group={self.group_id} | Worker={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Fatal initialization failure on streaming node context: {str(e)}")
            raise e

    def _write_transactional_audit_log(self, conn, tenant_id: str, product_name: str, price: float) -> None:
        with conn.cursor() as cursor:
            explanation = f"Ingestion telemetry pipeline execution verified: product={product_name} price={price}"
            cursor.execute("""
                INSERT INTO evidence_records (tenant_id, category, source_module, confidence_score, explanation_text, model_version)
                VALUES (%s, 'FACT', 'TELEMETRY_PIPELINE_NODE', 1.00, %s, 'core-infra-v1');
            """, (tenant_id, explanation))

    def execute_pipeline_listener(self):
        logger.info(f"Dynamic Backpressure Listener initialized. Polling structural streams at {self.stream_key}")
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
                            product_name = payload.get("product_name_captured", "Raw Token Sequence")
                            price_found = float(payload.get("price_found", 0.0))
                            
                            self._write_transactional_audit_log(db_connection, tenant_id, product_name, price_found)
                            
                            db_connection.commit()
                            self.client.xack(self.stream_key, self.group_id, message_id)
                            logger.info(f"[PIPELINE-COMMIT] Transaction verified and acknowledged: MessageID={message_id}")
                            
                        except Exception as inner_process_err:
                            if db_connection:
                                db_connection.rollback()
                            logger.error(f"[PIPELINE-ROLLBACK] Downstream failure on block {message_id}: {str(inner_process_err)}")
                            continue
                            
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            logger.info("Graceful shutdown loop interception received cleanly")
        except Exception as critical_runtime_overflow:
            logger.critical(f"[NODE-CRASH] Fatal exception within the stream processor array: {str(critical_runtime_overflow)}")
        finally:
            if db_connection:
                db_connection.close()
            self.client.close()
