# CEOPRO AI - Phase 1 Redis Architectural Blueprint

## 1. Service Configuration
- **Image**: `redis:7-alpine`
- **Container Name**: `ceopro_redis`
- **Network Port**: `6379`
- **Persistence**: Temporary data volume mapped to host (`redis_data`).

## 2. Strict Architectural Rule
Redis is strictly utilized as an **in-memory data structure store** for volatile data, fast lookups, and asynchronous coordination. It **MUST NOT** be used as a permanent source of truth for business assets like transactions, products, or AI forecasts. Permanent relational data belongs exclusively to PostgreSQL.

## 3. Phase 1 Responsibilities & Key-Value Patterns

### A. Background Job Task Status (AI Ingestion & Models)
When a user uploads a large CSV file or requests a new demand forecast via the AI layer, the process runs asynchronously. Redis tracks the live status of these background jobs.

- **Key Pattern**: `ceopro:tenant:{tenant_id}:job:{job_id}`
- **Data Type**: Hash
- **Example Value**:
  ```json
  {
    "status": "Processing",
    "module": "Demand_Prediction_XGBoost",
    "progress": "45%",
    "started_at": "2026-07-27T09:40:00Z"
  }
  ```

### B. Temporary API Rate Limiting (Web Application Team)
To secure the multi-tenant endpoints and prevent API abuse or brute-force attacks on sensitive business gateways.

- **Key Pattern**: `ceopro:ratelimit:{tenant_id}:user:{user_id}:window`
- **Data Type**: String (Integer with strict TTL/Expiry)
- **TTL**: `60 seconds`

### C. Temporary Dashboard Caching (Performance Optimization)
Frequently read business indicators (such as the main dashboard sales numbers) will be cached in Redis for short periods to avoid hitting the PostgreSQL database on every page refresh.

- **Key Pattern**: `ceopro:tenant:{tenant_id}:dashboard:summary_cache`
- **Data Type**: String (Serialized JSON string)
- **TTL**: `300 seconds (5 minutes)`
