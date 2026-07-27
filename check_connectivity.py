import sys
import time
import psycopg2
import redis
import urllib.request

print("====================================================")
print("?? CEOPRO AI - INFRASTRUCTURE CONNECTIVITY HEALTH CHECK")
print("====================================================\n")

all_passed = True

try:
    print("[Testing] Connecting to PostgreSQL on port 5432...")
    conn = psycopg2.connect(dbname="ceopro_platform", user="ceopro_admin", password="SecurePassword2026", host="localhost", port="5435", connect_timeout=3)
    print("? [SUCCESS] PostgreSQL is reachable! Relational core ready for Multi-Tenancy.")
    conn.close()
except Exception as e:
    print(f"? [FAILED] PostgreSQL Connection Refused -> {e}")
    all_passed = False

print("-" * 50)

try:
    print("[Testing] Pinging Redis In-Memory Store on port 6379...")
    r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=3)
    if r.ping():
        print("? [SUCCESS] Redis is reachable! Cache and async job queues are live.")
except Exception as e:
    print(f"? [FAILED] Redis Connection Refused -> {e}")
    all_passed = False

print("-" * 50)

try:
    print("[Testing] Checking MinIO S3 API Health Endpoint on port 9000...")
    response = urllib.request.urlopen("http://localhost:9000/minio/health/live", timeout=3)
    if response.getcode() == 200:
        print("? [SUCCESS] MinIO is reachable! Object buckets ready for raw CSV/Excel ingestion.")
except Exception as e:
    print(f"? [FAILED] MinIO Connection Refused or Unhealthy -> {e}")
    all_passed = False

print("\n====================================================")
if all_passed:
    print("?? [RESULT] ALL INFRASTRUCTURE HEALTH CHECKS PASSED SUCCESSFULLY!")
    sys.exit(0)
else:
    print("?? [RESULT] SOME SERVICES ARE UNREACHABLE. PLEASE CHECK DOCKER DESKTOP.")
    sys.exit(1)
