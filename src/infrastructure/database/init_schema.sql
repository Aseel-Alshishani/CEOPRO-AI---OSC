-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Multi-Tenancy Foundation Table (Multi-Country / Multi-Currency aware)
CREATE TABLE companies (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    country_code VARCHAR(2) NOT NULL,
    operating_countries TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    primary_currency VARCHAR(10) NOT NULL DEFAULT 'JOD',
    supported_currencies TEXT[] NOT NULL DEFAULT ARRAY['JOD'],
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Amman',
    preferred_language VARCHAR(5) NOT NULL DEFAULT 'en',
    supported_languages TEXT[] NOT NULL DEFAULT ARRAY['en'],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. User Management Table
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150),
    role VARCHAR(50) NOT NULL DEFAULT 'owner',
    preferred_language VARCHAR(5) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Core Products Table
CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    brand VARCHAR(155),
    category VARCHAR(155),
    current_price NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Sales and Operational Transactions Table (currency-traceable)
CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    quantity_sold INT NOT NULL CHECK (quantity_sold > 0),
    unit_price NUMERIC(10, 2) NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL,
    original_currency VARCHAR(10) NOT NULL,
    converted_amount NUMERIC(10, 2),
    converted_currency VARCHAR(10),
    exchange_rate NUMERIC(18, 8),
    conversion_source VARCHAR(100),
    conversion_timestamp TIMESTAMP WITH TIME ZONE,
    sale_source VARCHAR(50) DEFAULT 'POS',
    transaction_date TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Internal Business Inventory Table
CREATE TABLE inventory (
    inventory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID UNIQUE NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0,
    reorder_level INT DEFAULT 10,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Discovered Competitors Table
CREATE TABLE competitors (
    competitor_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    competitor_name VARCHAR(255) NOT NULL,
    country_code VARCHAR(2),
    relevance_score INT DEFAULT 0,
    market_activity_level VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Competitor and Market Prices Table (policy-aware, source-traceable)
CREATE TABLE competitor_prices (
    price_entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL REFERENCES competitors(competitor_id) ON DELETE CASCADE,
    product_name_captured VARCHAR(255) NOT NULL,
    price_found NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    is_exact_data BOOLEAN DEFAULT TRUE,
    collection_method VARCHAR(50) NOT NULL DEFAULT 'MANUAL',
    source_status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED',
    captured_by_user_id UUID REFERENCES users(user_id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED')),
    CONSTRAINT chk_source_status CHECK (source_status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED'))
);

-- 8. XGBoost Model Demand Forecasts Table
CREATE TABLE demand_forecasts (
    forecast_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    expected_demand INT NOT NULL,
    confidence_range_lower INT,
    confidence_range_upper INT,
    forecast_target_date DATE NOT NULL,
    model_version VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Unified Evidence Table (FACT / PREDICTION / RECOMMENDATION / ASSUMPTION / UNKNOWN)
CREATE TABLE evidence_records (
    evidence_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    category VARCHAR(20) NOT NULL,
    source_module VARCHAR(100) NOT NULL,
    source_record_ids JSONB,
    confidence_score NUMERIC(5, 2),
    explanation_text TEXT NOT NULL,
    model_version VARCHAR(50),
    country_context VARCHAR(2),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_evidence_category CHECK (category IN ('FACT', 'PREDICTION', 'RECOMMENDATION', 'ASSUMPTION', 'UNKNOWN'))
);

-- 10. Recommendation Outcome Tracking (Feedback Loop)
CREATE TABLE recommendation_outcomes (
    outcome_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evidence_id UUID NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    action_taken VARCHAR(20) NOT NULL DEFAULT 'ignored',
    action_timestamp TIMESTAMP WITH TIME ZONE,
    observed_result TEXT,
    evaluation_window VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_action_taken CHECK (action_taken IN ('accepted', 'modified', 'rejected', 'ignored'))
);

-- 11. RAG Documents Metadata Table
CREATE TABLE rag_documents_metadata (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    minio_object_key VARCHAR(512) NOT NULL,
    processed_status VARCHAR(50) DEFAULT 'Pending',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. Data Source Registry (Collection Policy Engine)
CREATE TABLE data_sources (
    data_source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES companies(tenant_id) ON DELETE CASCADE,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED',
    collection_method VARCHAR(50),
    justification TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_data_source_status CHECK (status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED'))
);

-- 13. Ingestion Job Tracking
CREATE TABLE ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    data_source_id UUID REFERENCES data_sources(data_source_id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    records_processed INT DEFAULT 0,
    records_failed INT DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 14. Model Version Registry
CREATE TABLE model_versions (
    model_version_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'development',
    trained_at TIMESTAMP WITH TIME ZONE,
    metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_model_status CHECK (status IN ('development', 'candidate', 'staging', 'production', 'archived'))
);

-- 15. Audit Log
CREATE TABLE audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES companies(tenant_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance and strict multi-tenancy isolation indexing
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE INDEX idx_transactions_tenant_date ON transactions(tenant_id, transaction_date);
CREATE INDEX idx_competitors_tenant ON competitors(tenant_id);
CREATE INDEX idx_competitor_prices_tenant ON competitor_prices(tenant_id);
CREATE INDEX idx_forecasts_tenant_date ON demand_forecasts(tenant_id, forecast_target_date);
CREATE INDEX idx_evidence_tenant_category ON evidence_records(tenant_id, category);
CREATE INDEX idx_outcomes_tenant ON recommendation_outcomes(tenant_id);
CREATE INDEX idx_data_sources_tenant ON data_sources(tenant_id);
CREATE INDEX idx_ingestion_jobs_tenant ON ingestion_jobs(tenant_id);
CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id);
