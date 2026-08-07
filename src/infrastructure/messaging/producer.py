"""
CEOPRO AI - Market Intelligence Message Broker Producer.
Thread-safe singleton producer enforcing a strict data contract on emitted events.
"""

import json
import logging
import os
import threading
import time
from typing import Dict, Any, Optional
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_PRODUCER_CORE")


class MarketIntelligenceProducer:
    _instance_lock = threading.Lock()
    _instance: Optional['MarketIntelligenceProducer'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(MarketIntelligenceProducer, cls).__new__(cls)
        return cls._instance

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self._circuit_open = False
        self._circuit_recovery_time = 0

        try:
            self.pool = redis.ConnectionPool(
                host=self.host,
                port=self.port,
                decode_responses=True,
                max_connections=50,
                socket_connect_timeout=3,
                socket_keepalive=True
            )
            self.client = redis.Redis(connection_pool=self.pool)
            self._initialized = True
            logger.info(f"Connection pool ready at {self.host}:{self.port}")
        except Exception as e:
            logger.critical(f"Failed to allocate connection pool: {str(e)}")
            raise e

    def _enforce_data_contract(self, payload: Dict[str, Any]) -> bool:
        required_schema = {
            "tenant_id": str,
            "product_name_captured": str,
            "price_found": (int, float),
            "currency": str
        }
        for field, expected_type in required_schema.items():
            if field not in payload:
                return False
            if not isinstance(payload[field], expected_type):
                return False
        return True

    def emit_market_event(self, stream_key: str, payload: Dict[str, Any]) -> Optional[str]:
        if not self._initialized:
            return None

        if self._circuit_open:
            if time.time() < self._circuit_recovery_time:
                logger.warning(f"Circuit open. Rejecting event for Stream={stream_key}")
                return None
            self._circuit_open = False

        if not self._enforce_data_contract(payload):
            logger.error(f"Rejected event due to invalid schema: {payload}")
            return None

        try:
            flattened_payload = {}
            for k, v in payload.items():
                flattened_payload[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)

            flattened_payload["_idempotency_token"] = f"token_{time.time_ns()}"

            message_id = self.client.xadd(stream_key, flattened_payload, id="*")
            logger.info(f"Event delivered to Stream={stream_key} MessageID={message_id}")
            return message_id
        except (redis.ConnectionError, redis.TimeoutError) as broker_err:
            logger.error(f"Broker connection failure: {str(broker_err)}")
            self._circuit_open = True
            self._circuit_recovery_time = time.time() + 30
            return None
        except Exception as unexpected_err:
            logger.error(f"Unexpected producer error: {str(unexpected_err)}")
            return None

    def purge_infrastructure_pool(self) -> None:
        try:
            self.pool.disconnect()
            logger.info("Connection pool disconnected.")
        except Exception as e:
            logger.error(f"Error during pool teardown: {str(e)}")
