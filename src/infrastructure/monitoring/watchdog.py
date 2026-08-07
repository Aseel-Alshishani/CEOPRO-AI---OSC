@'
"""
CEOPRO AI - Automated Asynchronous Telemetry Watchdog Core.
Executes non-blocking multi-threaded endpoint auditing loops.
"""

import json
import logging
import os
import time
import threading
import urllib.request
import psycopg2
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")
logger = logging.getLogger("CEOPRO_WATCHDOG")

class InfrastructureWatchdog:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")

        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
        self.error_threshold_pct = 5.0
        self.lock = threading.Lock()

    def _dispatch_alert(self, component: str, alert_type: str, details: str):
        with self.lock:
            logger.error(f"[ALERT] Component={component} Type={alert_type} Details={details}")
            if not self.webhook_url:
                return
            payload = {
                "text": f"[CEOPRO ALERT]\nComponent: {component}\nType: {alert_type}\nDetails: {details}\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            }
            try:
                req = urllib.request.Request(
                    self.webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    response.read()
            except Exception as e:
                logger.critical(f"Failed to send alert: {str(e)}")

    def _audit_postgres(self):
        try:
            conn = psycopg2.connect(self.db_url, connect_timeout=3)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COALESCE(SUM(records_processed), 0),
                        COALESCE(SUM(records_failed), 0)
                    FROM ingestion_jobs
                    WHERE created_at >= NOW() - INTERVAL '1 HOUR';
                    """
                )
                row = cursor.fetchone()
                total = int(row[0])
                failed = int(row[1])

                if total > 0:
                    error_rate = (failed / total) * 100
                    if error_rate > self.error_threshold_pct:
                        self._dispatch_alert(
                            "PostgreSQL-Ingestion",
                            "ERROR_RATE_EXCEEDED",
                            f"Error rate reached {error_rate:.2f}%"
                        )
            conn.close()
            logger.info("PostgreSQL check passed.")
        except Exception as e:
            self._dispatch_alert("PostgreSQL", "CONNECTION_LOST", str(e))

    def _audit_redis(self):
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, socket_timeout=3, decode_responses=True)
            if not r.ping():
                raise redis.RedisError("Redis did not respond to ping.")

            stream_length = r.xlen("market.intelligence.raw")
            if stream_length > 10000:
                self._dispatch_alert(
                    "Redis-Pipeline",
                    "STREAM_BACKLOG_OVERFLOW",
                    f"Backlog size reached {stream_length}"
                )
            r.close()
            logger.info("Redis check passed.")
        except Exception as e:
            self._dispatch_alert("Redis", "CONNECTION_LOST", str(e))

    def run_checks(self):
        logger.info("Starting infrastructure health checks.")
        t1 = threading.Thread(target=self._audit_postgres, name="PostgresAuditThread")
        t2 = threading.Thread(target=self._audit_redis, name="RedisAuditThread")

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)
        logger.info("Health checks complete.")

if __name__ == "__main__":
    watchdog = InfrastructureWatchdog()
    watchdog.run_checks()
'@ | Out-File -FilePath src/infrastructure/monitoring/watchdog.py -Encoding utf8
