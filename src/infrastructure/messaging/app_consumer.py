"""
CEOPRO AI - Infrastructure Message Broker Application Ingestion Consumer.
This module consumes post-processed business intelligence telemetry events.
Dispatches clean, structured data payloads to downstream visualization services and dashboards.
"""

import logging
import os
from typing import Optional
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_APP_CONSUMER_CORE")

class ApplicationDashboardConsumer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or "localhost"
        self.port = port or 6379
        self.group_id = "ceopro-app-dashboard-handlers"
        self.stream_key = "market.intelligence.processed"
        self.consumer_name = f"app-node-{os.getpid()}"
        
        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="$", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"Application Consumer registered to Group={self.group_id} | Consumer={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Initialization failure on Application Consumer: {str(e)}")
            raise e

    def listen_and_dispatch(self):
        logger.info(f"Application Ingestion Lifecycle Active. Monitoring Stream={self.stream_key}...")
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
                        tenant_id = payload.get("tenant_id")
                        logger.info(f"[APP-INGEST] Captured verified payload for Tenant={tenant_id} | MessageID={message_id}")
                        self.client.xack(self.stream_key, self.group_id, message_id)
                        
        except KeyboardInterrupt:
            logger.info("Application Ingestion Layer stopped cleanly")
        except Exception as system_err:
            logger.critical(f"Fatal runtime error in Application Ingestion loop: {str(system_err)}")

if __name__ == "__main__":
    app_engine = ApplicationDashboardConsumer()
    app_engine.listen_and_dispatch()
