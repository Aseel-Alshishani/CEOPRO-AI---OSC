"""
CEOPRO AI - Cryptographic Secret Rotation Engine.
Implements token lifecycle governance for X-Internal-Service-Token using HMAC-SHA256.
"""
import hmac
import hashlib
import logging
import os
import secrets
from typing import Optional, Tuple, List
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_SECURITY_ROTATOR")


class TokenRotationEngine:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.redis_key = "ceopro:auth:internal_tokens"
        self.grace_period = 172800

        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise RuntimeError("JWT_SECRET environment variable is not set. Cannot start token rotation engine.")
        self.secret_salt = secret.encode("utf-8")

        try:
            self.client = redis.Redis(host=self.host, port=self.port, decode_responses=True)
            logger.info("Token rotation engine bound to Redis.")
        except Exception as e:
            logger.critical(f"Failed to connect to Redis: {str(e)}")
            raise e

    def execute_secure_rotation(self) -> Tuple[str, List[str]]:
        """
        Generates a new token and places every previously active token into a
        time-limited grace window instead of removing them immediately.
        """
        try:
            raw_seed = secrets.token_bytes(32)
            new_token = hmac.new(self.secret_salt, raw_seed, hashlib.sha256).hexdigest()

            previously_active_tokens = list(self.client.smembers(self.redis_key))

            pipe = self.client.pipeline()
            pipe.sadd(self.redis_key, new_token)

            for old_token in previously_active_tokens:
                tracker_key = f"ceopro:auth:ttl_tracker:{old_token}"
                pipe.setex(tracker_key, self.grace_period, "active_grace")

            pipe.execute()
            logger.info(f"Rotation complete. New token issued. {len(previously_active_tokens)} token(s) entered grace window.")
            return new_token, previously_active_tokens
        except Exception as e:
            logger.error(f"Rotation failure: {str(e)}")
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
                    self.client.delete(tracker_key)
                    logger.warning("Legacy token expired and evicted.")
                    return False

            return True
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False


if __name__ == "__main__":
    rotator = TokenRotationEngine()
    rotator.execute_secure_rotation()
