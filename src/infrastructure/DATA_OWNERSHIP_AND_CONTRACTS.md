# CEOPRO AI - Phase 1 Data Ownership & Event Contracts Blueprint

## 1. Data & Service Ownership Matrix (Item 1.6)
To maintain integrity and prevent microservices from corrupting records, explicit read/write bounds are defined below:

| Entity / Data Type | Owning Microservice | Allowed Readers | Allowed Writers | Storage Location |
| :--- | :--- | :--- | :--- | :--- |
| **Tenants & Users** | Web Application Service | All Services | Web Application Service | PostgreSQL |
| **Raw Business Records** | Data Ingestion Pipeline | AI / ML Service | Web Application Service | MinIO (`ceopro-raw-ingestion`) |
| **ML Model Outputs** | AI / ML Service | Web Application Service | AI / ML Service | PostgreSQL & MinIO (`ceopro-ai-artifacts`) |
| **Market/Competitor Data** | AI Market Scraper Service | AI Advisor / Chatbot | AI Market Scraper Service | PostgreSQL |

## 2. Asynchronous Event Contracts (Item 1.5)
The platform coordinates background tasks asynchronously using defined schema event contracts:

### Event A: `data_raw_uploaded`
- **Producer**: Web Application Service (triggered upon a clean file upload)
- **Consumer**: Data Ingestion Framework
- **Payload Schema**:
  ```json
  {
    "event_id": "uuid-v4",
    "tenant_id": "uuid-v4",
    "file_key": "tenant_123/ingestion/sales_2026.csv",
    "timestamp": "2026-07-27T09:50:00Z"
  }
  ```

### Event B: `demand_forecast_requested`
- **Producer**: Web Application Service (triggered via dashboard or user cron schedule)
- **Consumer**: AI / ML Forecast Engine (`XGBoost` model pipeline)
- **Payload Schema**:
  ```json
  {
    "event_id": "uuid-v4",
    "tenant_id": "uuid-v4",
    "product_id": "uuid-v4",
    "horizon_days": 7,
    "timestamp": "2026-07-27T09:50:02Z"
  }
  ```
  ### Event C: campaign_image_requested
- **Producer**: Web Application Service (triggered from the Marketing module)
- **Consumer**: AI / ML Marketing Content Service
- **Payload Schema**:
  {
    "event_id": "uuid-v4",
    "tenant_id": "uuid-v4",
    "product_id": "uuid-v4",
    "style": "minimal",
    "tone": "sales-driven",
    "focus": "discount",
    "timestamp": "2026-07-27T09:50:04Z"
  }
