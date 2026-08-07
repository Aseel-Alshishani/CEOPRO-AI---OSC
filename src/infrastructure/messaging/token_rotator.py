"""
CEOPRO AI - Automated Cryptographic Secret Rotation Engine.
Implements Policy-as-Code for X-Internal-Service-Token using HMAC-SHA256.
"""

import hmac
import hashlib
import logging
import os
import secrets
import time
from typing import Optional, Tuple
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_SECURITY_ROTATOR")

class TokenRotationEngine:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.redis_key = "ceopro:auth:internal_tokens"
        self.grace_period = 172800
        self.secret_salt = os.getenv("JWT_SECRET", "QaWqd7VX3UDrHFuZCtML9YBwv4R1JK56P2OEGbhc").encode('utf-8')
        try:
            self.client = redis.Redis(host=host, port=port, decode_responses=True)
            logger.info("Cryptographic token subsystem bound to Redis core execution pool")
        except Exception as e:
            logger.critical(f"Failed to isolate token rotation context: {str(e)}")
            raise e

    def execute_secure_rotation(self) -> Tuple[str, Optional[str]]:
        try:
            raw_seed = secrets.token_bytes(32)
            new_token = hmac.new(self.secret_salt, raw_seed, hashlib.sha256).hexdigest()
            active_tokens = self.client.smembers(self.redis_key)
            legacy_token = list(active_tokens) if active_tokens else None

            pipe = self.client.pipeline()
            pipe.sadd(self.redis_key, new_token)
            if legacy_token:
                tracker_key = f"ceopro:auth:ttl_tracker:{legacy_token}"
                pipe.setex(tracker_key, self.grace_period, "active_grace")
            pipe.execute()
            logger.info("Cryptographic secret rotation executed successfully without telemetry leakage")
            return new_token, legacy_token
        except Exception as e:
            logger.error(f"Rotation failure within infrastructure runtime layer: {str(e)}")
            raise e

    def validate_incoming_token(self, token: str) -> bool:
        try:
            if not token or not isinstance(token, str):
                return False
            is_member = self.client.sismember(self.redis_key, token)
            if not is_member:
                return False
            tracker_key = f"ceopro:auth:ttl_tracker:{token}"
            if self.client.exists(tracker_key):
                ttl = self.client.ttl(tracker_key)
                if ttl <= 0:
                    self.client.srem(self.redis_key, token)
                    logger.warning(f"[SECURITY-EVICTION] Legacy cryptosign expired and evicted cleanly")
                    return False
            return True
        except Exception as e:
            logger.error(f"Token verification validation boundary overflow: {str(e)}")
            return False

if __name__ == "__main__":
    rotator = TokenRotationEngine()
    rotator.execute_secure_rotation()
