CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- TABLE 1: COMPANIES (Core Workspace Management)
CREATE TABLE companies (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    country_code VARCHAR(2) NOT NULL,
    operating_countries TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    primary_currency VARCHAR(3) NOT NULL,
    supported_currencies TEXT[] NOT NULL DEFAULT ARRAY['JOD']::TEXT[],
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Amman',
    preferred_language VARCHAR(5) NOT NULL DEFAULT 'en',
    supported_languages TEXT[] NOT NULL DEFAULT ARRAY['en']::TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER set_timestamp_companies BEFORE UPDATE ON companies FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 2: USERS (Global Centralized Authentication Directory)
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(150),
    preferred_language VARCHAR(5) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_email_format CHECK (email ~* '^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

CREATE TRIGGER set_timestamp_users BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 3: SYSTEM_ROLES (Dynamic RBAC Infrastructure Extensibility)
CREATE TABLE system_roles (
    role_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_key VARCHAR(50) UNIQUE NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO system_roles (role_key, role_name, permissions) VALUES 
('owner', 'Workspace Owner', '{"all": true}'),
('admin', 'Administrator', '{"manage_users": true, "manage_catalog": true}'),
('manager', 'Manager', '{"view_analytics": true, "manage_catalog": true}'),
('accountant', 'Accountant', '{"view_billing": true, "manage_billing": true}'),
('staff', 'Staff Member', '{"view_catalog": true}')
ON CONFLICT (role_key) DO NOTHING;

-- TABLE 4: TENANT_USERS (Pivot Table for Dynamic RBAC Authorization Mapping)
CREATE TABLE tenant_users (
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_key VARCHAR(50) NOT NULL REFERENCES system_roles(role_key),
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);

-- TABLE 5: PRODUCTS (Dynamic Multilingual Catalog Layer)
CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_name JSONB NOT NULL,
    brand JSONB,
    category JSONB,
    description JSONB,
    current_price NUMERIC(12, 4) NOT NULL CHECK (current_price >= 0),
    currency VARCHAR(3) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_by_user_id UUID,
    updated_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_product_source CHECK (source IN ('MANUAL', 'IMPORTED')),
    CONSTRAINT fk_products_creator FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL,
    CONSTRAINT fk_products_updater FOREIGN KEY (tenant_id, updated_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL
);

CREATE INDEX idx_products_tenant_deleted ON products(tenant_id, deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_products_name_gin ON products USING gin (product_name);
CREATE INDEX idx_products_category_gin ON products USING gin (category);

CREATE TRIGGER set_timestamp_products BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 6: PRODUCT_PRICE_HISTORY (Internal Financial Price Fluctuations)
CREATE TABLE product_price_history (
    price_history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    old_price NUMERIC(12, 4) CHECK (old_price >= 0),
    new_price NUMERIC(12, 4) NOT NULL CHECK (new_price >= 0),
    currency VARCHAR(3) NOT NULL,
    changed_by_user_id UUID,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_price_history_user FOREIGN KEY (tenant_id, changed_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL
);

CREATE INDEX idx_price_history_tenant_product ON product_price_history(tenant_id, product_id, changed_at DESC);

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_price_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_companies ON companies FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_tenant_users ON tenant_users FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_products ON products FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_price_history ON product_price_history FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- TABLE 7: INVENTORY (Warehouse Allocations & Safety Reorder Thresholds)
CREATE TABLE inventory (
    inventory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reorder_level INT DEFAULT 10 CHECK (reorder_level >= 0),
    updated_by_user_id UUID,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_inventory_tenant_product UNIQUE (tenant_id, product_id),
    CONSTRAINT fk_inventory_user FOREIGN KEY (tenant_id, updated_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL
);

CREATE TRIGGER set_timestamp_inventory BEFORE UPDATE ON inventory FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 8: CURRENCY_RATES (Global Multilateral Exchange Rate Directory)
CREATE TABLE currency_rates (
    rate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_currency VARCHAR(3) NOT NULL,
    target_currency VARCHAR(3) NOT NULL,
    rate NUMERIC(18, 8) NOT NULL CHECK (rate > 0),
    rate_date TIMESTAMP WITH TIME ZONE NOT NULL,
    source VARCHAR(100),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_currency_rate_time UNIQUE (base_currency, target_currency, rate_date)
);

-- TABLE 9: INVOICES (Sales Master Document Headers - Immutable Financial Storage)
CREATE TABLE invoices (
    invoice_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    sub_total NUMERIC(12, 4) NOT NULL CHECK (sub_total >= 0),
    tax_amount NUMERIC(12, 4) NOT NULL CHECK (tax_amount >= 0),
    discount_amount NUMERIC(12, 4) DEFAULT 0.0000 CHECK (discount_amount >= 0),
    grand_total NUMERIC(12, 4) NOT NULL CHECK (grand_total >= 0),
    currency VARCHAR(3) NOT NULL,
    sale_source VARCHAR(50) DEFAULT 'POS',
    issued_by_user_id UUID,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_invoice_per_tenant UNIQUE (tenant_id, invoice_number),
    CONSTRAINT fk_invoices_user FOREIGN KEY (tenant_id, issued_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL,
    CONSTRAINT chk_payment_method CHECK (payment_method IN ('CASH', 'CREDIT_CARD', 'APPLE_PAY', 'BANK_TRANSFER', 'MADA', 'FAWRY'))
);

CREATE INDEX idx_invoices_tenant_date ON invoices(tenant_id, issued_at DESC);

-- TABLE 10: INVOICE_ITEMS (Granular Sales Document Line Details - Immutable Financial Storage)
CREATE TABLE invoice_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 4) NOT NULL CHECK (unit_price >= 0),
    total_price NUMERIC(12, 4) NOT NULL CHECK (total_price >= 0),
    CONSTRAINT chk_item_total CHECK (total_price = (quantity * unit_price))
);

CREATE INDEX idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX idx_invoice_items_tenant ON invoice_items(tenant_id);

-- TABLE 11: GLOBAL_COMPETITORS (Canonical Marketplace Directory Registry)
CREATE TABLE global_competitors (
    competitor_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competitor_name VARCHAR(255) NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    website_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_competitor_regional_identity UNIQUE (competitor_name, country_code)
);

CREATE INDEX idx_global_competitors_regional_search ON global_competitors(country_code, competitor_name);

CREATE TRIGGER set_timestamp_global_competitors BEFORE UPDATE ON global_competitors FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 12: TENANT_COMPETITORS (Workspace Specific Target Focus Configurations)
CREATE TABLE tenant_competitors (
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL REFERENCES global_competitors(competitor_id) ON DELETE CASCADE,
    relevance_score INT DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
    market_activity_level VARCHAR(50),
    source VARCHAR(20) NOT NULL DEFAULT 'SYSTEM_DISCOVERED',
    added_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (tenant_id, competitor_id),
    CONSTRAINT fk_tenant_competitors_user FOREIGN KEY (tenant_id, added_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL,
    CONSTRAINT chk_competitor_source CHECK (source IN ('MANUAL', 'SYSTEM_DISCOVERED'))
);

CREATE INDEX idx_tenant_competitors_tenant_deleted ON tenant_competitors(tenant_id, deleted_at) WHERE deleted_at IS NULL;

CREATE TRIGGER set_timestamp_tenant_competitors BEFORE UPDATE ON tenant_competitors FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_competitors ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_inventory ON inventory FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_invoices ON invoices FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_invoice_items ON invoice_items FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_tenant_competitors ON tenant_competitors FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

    -- TABLE 13: COMPETITOR_PRODUCT_MAPPINGS (High Efficiency URL Resource Indexes)
CREATE TABLE competitor_product_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL,
    competitor_product_url TEXT NOT NULL,
    product_name_captured VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_mappings_tenant_comp FOREIGN KEY (tenant_id, competitor_id) REFERENCES tenant_competitors(tenant_id, competitor_id) ON DELETE RESTRICT,
    CONSTRAINT uq_tenant_product_competitor UNIQUE (tenant_id, product_id, competitor_id)
);

CREATE INDEX idx_mappings_tenant_product_deleted ON competitor_product_mappings(tenant_id, product_id, deleted_at) WHERE deleted_at IS NULL;

CREATE TRIGGER set_timestamp_competitor_product_mappings BEFORE UPDATE ON competitor_product_mappings FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 14: COMPETITOR_PRICES (High Performance Numerical Delta Tracker)
CREATE TABLE competitor_prices (
    price_entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    mapping_id UUID NOT NULL REFERENCES competitor_product_mappings(mapping_id) ON DELETE CASCADE,
    price_found NUMERIC(12, 4) NOT NULL CHECK (price_found >= 0),
    currency VARCHAR(3) NOT NULL,
    collection_method VARCHAR(50) NOT NULL DEFAULT 'WEB_SCRAPER',
    captured_by_user_id UUID,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_prices_tenant_user FOREIGN KEY (tenant_id, captured_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE SET NULL,
    CONSTRAINT chk_price_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED', 'WEB_SCRAPER'))
);

CREATE INDEX idx_competitor_prices_tenant_mapping ON competitor_prices(tenant_id, mapping_id, captured_at DESC);

-- TABLE 15: REVIEWS (Multi-Source Index Supporting Dense Semantic Vectors)
CREATE TABLE reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    subject_type VARCHAR(20) NOT NULL,
    product_id UUID REFERENCES products(product_id) ON DELETE CASCADE,
    competitor_id UUID,
    source_platform VARCHAR(100),
    review_text TEXT NOT NULL,
    rating NUMERIC(3, 1),
    review_language VARCHAR(5),
    review_date TIMESTAMP WITH TIME ZONE,
    collection_method VARCHAR(50) NOT NULL DEFAULT 'MANUAL',
    source_status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED',
    review_vector vector(1024),
    embedding_model_version VARCHAR(50) DEFAULT 'BAAI/bge-m3',
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_review_subject_type CHECK (subject_type IN ('PRODUCT', 'COMPETITOR', 'BUSINESS')),
    CONSTRAINT chk_review_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED')),
    CONSTRAINT chk_review_source_status CHECK (source_status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED')),
    CONSTRAINT fk_reviews_tenant_comp FOREIGN KEY (tenant_id, competitor_id) REFERENCES tenant_competitors(tenant_id, competitor_id) ON DELETE RESTRICT,
    CONSTRAINT chk_review_subject_consistency CHECK (
        (subject_type = 'PRODUCT' AND product_id IS NOT NULL AND competitor_id IS NULL) OR
        (subject_type = 'COMPETITOR' AND competitor_id IS NOT NULL AND product_id IS NULL) OR
        (subject_type = 'BUSINESS' AND product_id IS NULL AND competitor_id IS NULL)
    )
);

CREATE INDEX idx_reviews_tenant_subject_deleted ON reviews(tenant_id, subject_type, deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_reviews_vector_hnsw ON reviews USING hnsw (review_vector vector_cosine_ops);

CREATE TRIGGER set_timestamp_reviews BEFORE UPDATE ON reviews FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 16: SENTIMENT_RESULTS (Model Classification Probabilities Matrix)
CREATE TABLE sentiment_results (
    sentiment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    review_id UUID NOT NULL REFERENCES reviews(review_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    label VARCHAR(20) NOT NULL,
    positive_probability NUMERIC(5, 4) CHECK (positive_probability BETWEEN 0 AND 1),
    neutral_probability NUMERIC(5, 4) CHECK (neutral_probability BETWEEN 0 AND 1),
    negative_probability NUMERIC(5, 4) CHECK (negative_probability BETWEEN 0 AND 1),
    confidence NUMERIC(5, 4) CHECK (confidence BETWEEN 0 AND 1),
    model_version VARCHAR(50),
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_sentiment_label CHECK (label IN ('positive', 'neutral', 'negative')),
    CONSTRAINT uq_sentiment_per_review UNIQUE (tenant_id, review_id)
);

CREATE INDEX idx_sentiment_results_tenant_label ON sentiment_results(tenant_id, label);

-- TABLE 17: DEMAND_FORECASTS (XGBoost Future Demand Expectations Logs)
CREATE TABLE demand_forecasts (
    forecast_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    forecast_run_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    forecast_target_date DATE NOT NULL,
    expected_demand INT NOT NULL CHECK (expected_demand >= 0),
    confidence_range_lower INT NOT NULL CHECK (confidence_range_lower >= 0),
    confidence_range_upper INT NOT NULL CHECK (confidence_range_upper >= 0),
    model_accuracy_score NUMERIC(5, 4),
    model_version VARCHAR(50) DEFAULT 'XGBOOST_V1.2',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_confidence_range CHECK (confidence_range_upper >= confidence_range_lower)
);

CREATE INDEX idx_demand_forecasts_tenant_product ON demand_forecasts(tenant_id, product_id, forecast_target_date DESC);

-- TABLE 18: EVIDENCE_RECORDS (Unified AI Reasoning & Business Assertions Log)
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

CREATE INDEX idx_evidence_records_tenant_category ON evidence_records(tenant_id, category);

ALTER TABLE competitor_product_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE sentiment_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE demand_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_competitor_product_mappings ON competitor_product_mappings FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_competitor_prices ON competitor_prices FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_reviews ON reviews FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_sentiment_results ON sentiment_results FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_demand_forecasts ON demand_forecasts FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_evidence_records ON evidence_records FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- TABLE 19: RECOMMENDATION_OUTCOMES (Closed-Loop Model Evaluation Tracer)
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

CREATE INDEX idx_recommendation_outcomes_tenant_lookup ON recommendation_outcomes(tenant_id, action_taken);

-- TABLE 20: SYSTEM_ALERTS (Enterprise Pipeline Real-Time Notification Tracker)
CREATE TABLE system_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    message_payload TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    linked_entity_type VARCHAR(50),
    linked_entity_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_alert_severity CHECK (severity IN ('info', 'warning', 'critical'))
);

CREATE INDEX idx_system_alerts_tenant_unread ON system_alerts(tenant_id, is_read) WHERE is_read IS FALSE;

-- TABLE 21: RAG_DOCUMENTS_METADATA (Physical File Pointer Manifests)
CREATE TABLE rag_documents_metadata (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    minio_object_key VARCHAR(512) NOT NULL,
    processed_status VARCHAR(50) DEFAULT 'Pending',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_rag_docs_tenant_deleted ON rag_documents_metadata(tenant_id, deleted_at) WHERE deleted_at IS NULL;

CREATE TRIGGER set_timestamp_rag_documents_metadata BEFORE UPDATE ON rag_documents_metadata FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 22: RAG_DOCUMENT_CHUNKS (Contextual Text Splitting & Embedding Depot)
CREATE TABLE rag_document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES rag_documents_metadata(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_document_chunk_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_rag_chunks_tenant_document ON rag_document_chunks(tenant_id, document_id);
CREATE INDEX idx_rag_chunks_vector_hnsw ON rag_document_chunks USING hnsw (embedding vector_cosine_ops);

-- TABLE 23: DATA_SOURCES (Collection Compliance Policy Boundaries Engine)
CREATE TABLE data_sources (
    data_source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES companies(tenant_id) ON DELETE CASCADE,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED',
    collection_method VARCHAR(50),
    justification TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_data_source_status CHECK (status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED'))
);

CREATE INDEX idx_data_sources_tenant_deleted ON data_sources(tenant_id, deleted_at) WHERE deleted_at IS NULL;

CREATE TRIGGER set_timestamp_data_sources BEFORE UPDATE ON data_sources FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 24: INGESTION_JOBS (Pipeline Synchronization Execution Runs)
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

CREATE INDEX idx_ingestion_jobs_tenant_status ON ingestion_jobs(tenant_id, status);

-- TABLE 25: IMPORT_STAGING_ROWS (Intermediate Data Validation Sandbox)
CREATE TABLE import_staging_rows (
    staging_row_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES ingestion_jobs(job_id) ON DELETE CASCADE,
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

CREATE INDEX idx_import_staging_tenant_job ON import_staging_rows(tenant_id, job_id, validation_status);

CREATE TRIGGER set_timestamp_import_staging_rows BEFORE UPDATE ON import_staging_rows FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 26: AUDIT_LOGS (Global Security Compliance Event Directory)
CREATE TABLE audit_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    target_entity_id UUID,
    old_state JSONB,
    new_state JSONB,
    ip_address VARCHAR(45),
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_tenant_entity ON audit_logs(tenant_id, target_table, logged_at DESC);

ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_documents_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_staging_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_recommendation_outcomes ON recommendation_outcomes FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_system_alerts ON system_alerts FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_rag_documents_metadata ON rag_documents_metadata FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_rag_document_chunks ON rag_document_chunks FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_ingestion_jobs ON ingestion_jobs FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_import_staging_rows ON import_staging_rows FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_audit_logs ON audit_logs FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_select_data_sources ON data_sources FOR SELECT USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid OR tenant_id IS NULL);
CREATE POLICY tenant_modify_data_sources ON data_sources FOR INSERT WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_update_data_sources ON data_sources FOR UPDATE USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
CREATE POLICY tenant_delete_data_sources ON data_sources FOR DELETE USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
