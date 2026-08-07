"""
CEOPRO AI - Infrastructure Message Broker Producer Core.
This module implements a thread-safe, high-throughput Redis Stream producer.
It handles structural payload ingestion from multi-vector market scraping engines.
"""

import json
import logging
import threading
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
            
        self.host = host or "localhost"
        self.port = port or 6379
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self._initialized = True
            logger.info(f"Stream Producer successfully connected to broker at {self.host}:{self.port}")
        except Exception as e:
            logger.critical(f"Failed to initialize stream producer instance: {str(e)}")
            raise e

    def emit_market_event(self, stream_key: str, payload: Dict[str, Any]) -> Optional[str]:
        if not self._initialized:
            logger.error("Producer context remains uninitialized")
            return None
        try:
            flattened_payload = {k: str(v) if isinstance(v, (dict, list)) else v for k, v in payload.items()}
            message_id = self.client.xadd(stream_key, flattened_payload, id="*")
            logger.info(f"[PRODUCER-SUCCESS] Verified ingestion to Stream={stream_key} | MessageID={message_id}")
            return message_id
        except redis.RedisError as re:
            logger.error(f"Broker connection failure during delivery on stream {stream_key}: {str(re)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected operational overflow while publishing event: {str(e)}")
            return None
