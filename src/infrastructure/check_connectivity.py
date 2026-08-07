import os
import sys
import psycopg2
import redis
import urllib.request

print("====================================================")
print("CEOPRO AI - INFRASTRUCTURE CONNECTIVITY HEALTH CHECK")
print("====================================================\n")

all_passed = True

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")

try:
    print(f"[Testing] Connecting to PostgreSQL on port {POSTGRES_PORT}...")
    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        connect_timeout=3,
    )
    print("[SUCCESS] PostgreSQL is reachable. Relational core ready for Multi-Tenancy.")
    conn.close()
except Exception as e:
    print(f"[FAILED] PostgreSQL connection refused -> {e}")
    all_passed = False

print("-" * 50)

try:
    print(f"[Testing] Pinging Redis on port {REDIS_PORT}...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=3)
    if r.ping():
        print("[SUCCESS] Redis is reachable. Cache and async job queues are live.")
except Exception as e:
    print(f"[FAILED] Redis connection refused -> {e}")
    all_passed = False

print("-" * 50)

try:
    print("[Testing] Checking MinIO S3 API health endpoint...")
    response = urllib.request.urlopen(f"{MINIO_ENDPOINT}/minio/health/live", timeout=3)
    if response.getcode() == 200:
        print("[SUCCESS] MinIO is reachable. Object buckets ready for raw CSV/Excel ingestion.")
except Exception as e:
    print(f"[FAILED] MinIO connection refused or unhealthy -> {e}")
    all_passed = False

print("\n====================================================")
if all_passed:
    print("[RESULT] ALL INFRASTRUCTURE HEALTH CHECKS PASSED SUCCESSFULLY.")
    sys.exit(0)
else:
    print("[RESULT] SOME SERVICES ARE UNREACHABLE. PLEASE CHECK DOCKER DESKTOP.")
    sys.exit(1)
