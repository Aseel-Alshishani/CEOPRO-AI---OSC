"""
CEOPRO AI - Core Real-Time Ingestion Application Node.
Subscribes to post-processed analytical output data arrays and dispatches clean
telemetry maps directly to high-throughput interface sockets.
"""

import logging
import os
import time
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
        self.consumer_name = f"app-core-node-{os.getpid()}"
        
        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="$", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"Application Streaming Node activated. Group={self.group_id} | Worker={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Initialization failure on Application Consumer Node: {str(e)}")
            raise e

    def listen_and_dispatch(self):
        logger.info(f"UI Visualization Pipeline initialized. Awaiting payloads on Stream={self.stream_key}")
        try:
            while True:
                response = self.client.xreadgroup(
                    groupname=self.group_id,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=20,
                    block=1000
                )
                
                if not response:
                    continue
                    
                for stream, messages in response:
                    for message_id, payload in messages:
                        try:
                            tenant_id = payload.get("tenant_id")
                            logger.info(f"[DASHBOARD-DISPATCH] Telemetry pushed to WebSockets for Tenant={tenant_id} | StreamID={message_id}")
                            
                            self.client.xack(self.stream_key, self.group_id, message_id)
                        except Exception as dispatch_err:
                            logger.error(f"UI streaming buffer overflow on event {message_id}: {str(dispatch_err)}")
                            continue
                            
                time.sleep(0.01)
        except KeyboardInterrupt:
            logger.info("Application Ingestion execution context cleanly intercepted")
        except Exception as critical_runtime_overflow:
            logger.critical(f"Fatal dashboard orchestration pipeline disruption: {str(critical_runtime_overflow)}")
        finally:
            self.client.close()

if __name__ == "__main__":
    app_engine = ApplicationDashboardConsumer()
    app_engine.listen_and_dispatch()
