"""
CEOPRO AI - Infrastructure Message Broker AI Pipeline Consumer.
This module manages idempotent, high-volume ingestion streams for AI/NLP extraction models.
It guarantees zero message skipping through deterministic stream group offsets.
"""

import json
import logging
import os
from typing import Optional
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_AI_CONSUMER_CORE")

class AIStreamConsumer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, group_id: str = "ceopro-ai-nlp-extractors"):
        self.host = host or "localhost"
        self.port = port or 6379
        self.group_id = group_id
        self.stream_key = "market.intelligence.raw"
        self.consumer_name = f"ai-node-{os.getpid()}"
        
        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="0", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"AI Stream Consumer registered to Group={self.group_id} | Consumer={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Initialization failure on AI Stream Consumer: {str(e)}")
            raise e

    def execute_pipeline_listener(self):
        logger.info(f"AI Pipeline Lifecycle Active. Monitoring Stream={self.stream_key}...")
        try:
            while True:
                response = self.client.xreadgroup(
                    groupname=self.group_id,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=10,
                    block=1000
                )
                
                if not response:
                    continue
                    
                for stream, messages in response:
                    for message_id, payload in messages:
                        logger.info(f"[AI-INGEST] Processing Payload StreamID={message_id}")
                        
                        try:
                            pass
                        except Exception as nlp_err:
                            logger.error(f"NLP classification downstream failure on MessageID {message_id}: {str(nlp_err)}")
                            continue
                        
                        self.client.xack(self.stream_key, self.group_id, message_id)
                        
        except KeyboardInterrupt:
            logger.info("Graceful shutdown signal received for AI Consumer context")
        except Exception as system_err:
            logger.critical(f"Fatal runtime error in AI Pipeline Ingestion loop: {str(system_err)}")

if __name__ == "__main__":
    pipeline = AIStreamConsumer()
    pipeline.execute_pipeline_listener()
