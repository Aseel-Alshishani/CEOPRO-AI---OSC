-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

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

-- 3. Core Products Table (manual entry and imported entries share one table)
CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    brand VARCHAR(155),
    category VARCHAR(155),
    current_price NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10),
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    created_by_user_id UUID REFERENCES users(user_id),
    updated_by_user_id UUID REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_product_source CHECK (source IN ('MANUAL', 'IMPORTED'))
);

-- 4. Product Price History (required for pricing and demand analysis)
CREATE TABLE product_price_history (
    price_history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    old_price NUMERIC(10, 2),
    new_price NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    changed_by_user_id UUID REFERENCES users(user_id),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Sales and Operational Transactions Table (currency-traceable)
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

-- 6. Internal Business Inventory Table
CREATE TABLE inventory (
    inventory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID UNIQUE NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0,
    reorder_level INT DEFAULT 10,
    updated_by_user_id UUID REFERENCES users(user_id),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Discovered and Manually Added Competitors Table
CREATE TABLE competitors (
    competitor_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    competitor_name VARCHAR(255) NOT NULL,
    country_code VARCHAR(2),
    relevance_score INT DEFAULT 0,
    market_activity_level VARCHAR(50),
    source VARCHAR(20) NOT NULL DEFAULT 'SYSTEM_DISCOVERED',
    added_by_user_id UUID REFERENCES users(user_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_competitor_source CHECK (source IN ('MANUAL', 'SYSTEM_DISCOVERED'))
);

-- 8. Competitor and Market Prices Table (policy-aware, source-traceable)
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
    CONSTRAINT chk_price_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED')),
    CONSTRAINT chk_price_source_status CHECK (source_status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED'))
);

-- 9. Reviews Table (own products, competitors, or general business sentiment)
CREATE TABLE reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    subject_type VARCHAR(20) NOT NULL,
    product_id UUID REFERENCES products(product_id) ON DELETE CASCADE,
    competitor_id UUID REFERENCES competitors(competitor_id) ON DELETE CASCADE,
    source_platform VARCHAR(100),
    review_text TEXT,
    rating NUMERIC(3, 1),
    review_language VARCHAR(5),
    review_date TIMESTAMP WITH TIME ZONE,
    collection_method VARCHAR(50) NOT NULL DEFAULT 'MANUAL',
    source_status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED',
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_review_subject_type CHECK (subject_type IN ('PRODUCT', 'COMPETITOR', 'BUSINESS')),
    CONSTRAINT chk_review_subject_consistency CHECK (
        (subject_type = 'PRODUCT' AND product_id IS NOT NULL AND competitor_id IS NULL) OR
        (subject_type = 'COMPETITOR' AND competitor_id IS NOT NULL AND product_id IS NULL) OR
        (subject_type = 'BUSINESS' AND product_id IS NULL AND competitor_id IS NULL)
    ),
    CONSTRAINT chk_review_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED')),
    CONSTRAINT chk_review_source_status CHECK (source_status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED'))
);

-- 10. Sentiment Analysis Results Table
CREATE TABLE sentiment_results (
    sentiment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    review_id UUID NOT NULL REFERENCES reviews(review_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    label VARCHAR(20) NOT NULL,
    positive_probability NUMERIC(5, 4),
    neutral_probability NUMERIC(5, 4),
    negative_probability NUMERIC(5, 4),
    confidence NUMERIC(5, 4),
    model_version VARCHAR(50),
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_sentiment_label CHECK (label IN ('positive', 'neutral', 'negative'))
);

-- 11. XGBoost Model Demand Forecasts Table
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

-- 12. Unified Evidence Table (FACT / PREDICTION / RECOMMENDATION / ASSUMPTION / UNKNOWN)
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

-- 13. Recommendation Outcome Tracking (Feedback Loop)
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

-- 14. RAG Documents Metadata Table
CREATE TABLE rag_documents_metadata (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    minio_object_key VARCHAR(512) NOT NULL,
    processed_status VARCHAR(50) DEFAULT 'Pending',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 15. RAG Document Chunks with Embeddings (pgvector)
-- Dimension 1024 covers the largest realistic open-source multilingual embedding
-- models (BGE-M3, multilingual-e5-large). This does not change based on GPU vs CPU
-- availability -- it is bounded by the open-source/no-mandatory-paid-API constraint,
-- not by hardware. A smaller model's output still fits into this column.
CREATE TABLE rag_document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES rag_documents_metadata(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 16. Currency Exchange Rates Table
CREATE TABLE currency_rates (
    rate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_currency VARCHAR(10) NOT NULL,
    target_currency VARCHAR(10) NOT NULL,
    rate NUMERIC(18, 8) NOT NULL,
    rate_date DATE NOT NULL,
    source VARCHAR(100),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_currency_rate UNIQUE (base_currency, target_currency, rate_date)
);

-- 17. Import Staging Rows (preview and edit before committing to real tables)
CREATE TABLE import_staging_rows (
    staging_row_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    row_number INT NOT NULL,
    raw_data JSONB NOT NULL,
    mapped_data JSONB,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'needs_review',
    validation_errors JSONB,
    is_edited_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    final_data JSONB,
    committed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_staging_validation_status CHECK (validation_status IN ('valid', 'needs_review', 'rejected'))
);

-- 18. Data Source Registry (Collection Policy Engine)
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

-- 19. Ingestion Job Tracking
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

ALTER TABLE import_staging_rows
    ADD CONSTRAINT fk_staging_job FOREIGN KEY (job_id) REFERENCES ingestion_jobs(job_id) ON DELETE CASCADE;

-- 20. Model Version Registry
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

-- 21. Audit Log
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
CREATE INDEX idx_products_tenant ON products(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_price_history_product ON product_price_history(product_id);
CREATE INDEX idx_transactions_tenant_date ON transactions(tenant_id, transaction_date);
CREATE INDEX idx_inventory_tenant ON inventory(tenant_id);
CREATE INDEX idx_competitors_tenant ON competitors(tenant_id) WHERE is_active = TRUE;
CREATE INDEX idx_competitor_prices_tenant ON competitor_prices(tenant_id);
CREATE INDEX idx_reviews_tenant ON reviews(tenant_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
CREATE INDEX idx_reviews_competitor ON reviews(competitor_id);
CREATE INDEX idx_sentiment_review ON sentiment_results(review_id);
CREATE INDEX idx_forecasts_tenant_date ON demand_forecasts(tenant_id, forecast_target_date);
CREATE INDEX idx_evidence_tenant_category ON evidence_records(tenant_id, category);
CREATE INDEX idx_outcomes_tenant ON recommendation_outcomes(tenant_id);
CREATE INDEX idx_rag_chunks_document ON rag_document_chunks(document_id);
CREATE INDEX idx_currency_rates_lookup ON currency_rates(base_currency, target_currency, rate_date);
CREATE INDEX idx_staging_job ON import_staging_rows(job_id);
CREATE INDEX idx_data_sources_tenant ON data_sources(tenant_id);
CREATE INDEX idx_ingestion_jobs_tenant ON ingestion_jobs(tenant_id);
CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id);

-- OPTIONAL: create this AFTER real embeddings exist, not on an empty table.
-- Adjust "lists" based on expected row count once you have real data volume.
-- CREATE INDEX idx_rag_chunks_embedding ON rag_document_chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ==============================================================================
-- CEOPRO AI - ENTERPRISE MULTI-TENANCY ROW-LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE sentiment_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE demand_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_documents_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_staging_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_users_policy ON users 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_products_policy ON products 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_history_policy ON product_price_history 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_transactions_policy ON transactions 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_inventory_policy ON inventory 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_competitors_policy ON competitors 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_cprices_policy ON competitor_prices 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_reviews_policy ON reviews 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_sentiment_policy ON sentiment_results 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_forecasts_policy ON demand_forecasts 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_evidence_policy ON evidence_records 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_outcomes_policy ON recommendation_outcomes 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_rag_metadata_policy ON rag_documents_metadata 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_rag_chunks_policy ON rag_document_chunks 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_staging_policy ON import_staging_rows 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_sources_policy ON data_sources 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_jobs_policy ON ingestion_jobs 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_isolation_audit_policy ON audit_logs 
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
