"""
CEOPRO AI - Dashboard Stream Consumer.
Consumes processed market intelligence events. No dashboard/backend service
exists yet to forward them to (PENDING_ACTIONS.md), so this currently only
logs and acknowledges each message - a real dispatch step (e.g. writing to a
cache the dashboard reads, or a websocket push) needs to land alongside
whatever backend eventually owns the dashboard layer.
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
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.group_id = "ceopro-app-dashboard-handlers"
        self.stream_key = "market.intelligence.processed"
        self.consumer_name = f"app-core-node-{os.getpid()}"

        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            try:
                self.client.xgroup_create(self.stream_key, self.group_id, id="$", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            logger.info(f"Dashboard consumer active. Group={self.group_id} Worker={self.consumer_name}")
        except Exception as e:
            logger.critical(f"Initialization failure: {str(e)}")
            raise e

    def listen_and_dispatch(self):
        logger.info(f"Listening on stream {self.stream_key}")
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
                            logger.info(
                                f"Acknowledged update for Tenant={tenant_id} StreamID={message_id} (no dispatch target yet)"
                            )
                            self.client.xack(self.stream_key, self.group_id, message_id)
                        except Exception as dispatch_err:
                            logger.error(f"Dispatch failure on event {message_id}: {str(dispatch_err)}")
                            continue

                time.sleep(0.01)
        except KeyboardInterrupt:
            logger.info("Shutdown signal received.")
        except Exception as critical_runtime_error:
            logger.critical(f"Fatal dashboard consumer error: {str(critical_runtime_error)}")
        finally:
            self.client.close()


if __name__ == "__main__":
    app_engine = ApplicationDashboardConsumer()
    app_engine.listen_and_dispatch()
