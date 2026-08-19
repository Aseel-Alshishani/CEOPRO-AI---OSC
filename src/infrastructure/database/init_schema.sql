CREATE OR REPLACE FUNCTION get_current_tenant()
RETURNS UUID AS $$
DECLARE
    tenant_str TEXT;
BEGIN
    tenant_str := current_setting('app.current_tenant_id', true);
    IF tenant_str IS NULL OR tenant_str = '' THEN
        RETURN NULL;
    END IF;
    RETURN tenant_str::uuid;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- TABLE 1: COMPANIES
CREATE TABLE IF NOT EXISTS companies (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    country_code VARCHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    operating_countries TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    primary_currency VARCHAR(3) NOT NULL CHECK (primary_currency ~ '^[A-Z]{3}$'),
    supported_currencies TEXT[] NOT NULL DEFAULT ARRAY['JOD']::TEXT[],
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Amman',
    preferred_language VARCHAR(5) NOT NULL DEFAULT 'en',
    supported_languages TEXT[] NOT NULL DEFAULT ARRAY['en']::TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
);

CREATE TRIGGER set_timestamp_companies 
BEFORE UPDATE ON companies 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 2: USERS
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(150),
    preferred_language VARCHAR(5) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_email_format CHECK (email ~* '^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (LOWER(email));

CREATE TRIGGER set_timestamp_users 
BEFORE UPDATE ON users 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 3: SYSTEM_ROLES
CREATE TABLE IF NOT EXISTS system_roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- TABLE 4: TENANT_USERS
CREATE TABLE IF NOT EXISTS tenant_users (
    tenant_user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_key VARCHAR(50) NOT NULL REFERENCES system_roles(role_key),
    removed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_user_composite_perimeter ON tenant_users(tenant_id, user_id);

-- TABLE 5: PRODUCTS
CREATE TABLE IF NOT EXISTS products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_name JSONB NOT NULL,
    brand JSONB,
    category JSONB,
    description JSONB,
    current_price NUMERIC(12, 4) NOT NULL CHECK (current_price >= 0),
    currency VARCHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_by_user_id UUID,
    updated_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    CONSTRAINT chk_product_source CHECK (source IN ('MANUAL', 'IMPORTED')),
    CONSTRAINT fk_products_creator FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_products_updater FOREIGN KEY (tenant_id, updated_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_tenant_product_perimeter UNIQUE (tenant_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_products_tenant_deleted ON products(tenant_id, deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_products_name_gin ON products USING gin (product_name);

CREATE TRIGGER set_timestamp_products 
BEFORE UPDATE ON products 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 6: PRODUCT_PRICE_HISTORY
CREATE TABLE IF NOT EXISTS product_price_history (
    price_history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    old_price NUMERIC(12, 4) CHECK (old_price >= 0),
    new_price NUMERIC(12, 4) NOT NULL CHECK (new_price >= 0),
    currency VARCHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    changed_by_user_id UUID,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_price_history_product_isolated FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE CASCADE,
    CONSTRAINT fk_price_history_user_isolated FOREIGN KEY (tenant_id, changed_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_price_history_tenant_product ON product_price_history(tenant_id, product_id, changed_at DESC);

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_price_history ENABLE ROW LEVEL SECURITY;

ALTER TABLE companies FORCE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_users FORCE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
ALTER TABLE product_price_history FORCE ROW LEVEL SECURITY;

CREATE POLICY insert_companies_onboarding ON companies FOR INSERT WITH CHECK (get_current_tenant() IS NULL OR tenant_id = get_current_tenant());
CREATE POLICY select_companies_isolated ON companies FOR SELECT USING (tenant_id = get_current_tenant() AND deleted_at IS NULL);
CREATE POLICY update_companies_isolated ON companies FOR UPDATE USING (tenant_id = get_current_tenant());
CREATE POLICY delete_companies_isolated ON companies FOR DELETE USING (tenant_id = get_current_tenant());

CREATE POLICY insert_users_signup ON users FOR INSERT WITH CHECK (true);
CREATE POLICY select_users_perimeter ON users FOR SELECT USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid 
    OR EXISTS (SELECT 1 FROM tenant_users WHERE tenant_users.user_id = users.user_id AND tenant_users.tenant_id = get_current_tenant())
);
CREATE POLICY update_users_self ON users FOR UPDATE USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY isolation_tenant_users ON tenant_users FOR ALL USING (tenant_id = get_current_tenant());

CREATE POLICY select_products_isolated ON products FOR SELECT USING (tenant_id = get_current_tenant() AND deleted_at IS NULL);
CREATE POLICY update_products_isolated ON products FOR UPDATE USING (tenant_id = get_current_tenant());
CREATE POLICY insert_products_isolated ON products FOR INSERT WITH CHECK (tenant_id = get_current_tenant());
CREATE POLICY delete_products_isolated ON products FOR DELETE USING (tenant_id = get_current_tenant());

CREATE POLICY isolation_price_history ON product_price_history FOR ALL USING (tenant_id = get_current_tenant());
-- TABLE 7: INVENTORY
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    reorder_level INT NOT NULL DEFAULT 10 CHECK (reorder_level >= 0),
    safety_stock INT NOT NULL DEFAULT 5 CHECK (safety_stock >= 0),
    warehouse_location VARCHAR(150),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_inventory_product_isolated FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_inventory_perimeter UNIQUE (tenant_id, inventory_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_tenant_product ON inventory(tenant_id, product_id);

CREATE TRIGGER set_timestamp_inventory 
BEFORE UPDATE ON inventory 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 8: CURRENCY_RATES
CREATE TABLE IF NOT EXISTS currency_rates (
    rate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency VARCHAR(3) NOT NULL CHECK (from_currency ~ '^[A-Z]{3}$'),
    to_currency VARCHAR(3) NOT NULL CHECK (to_currency ~ '^[A-Z]{3}$'),
    exchange_rate NUMERIC(12, 6) NOT NULL CHECK (exchange_rate > 0),
    last_fetched TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_currency_pair UNIQUE (from_currency, to_currency)
);

-- TABLE 9: INVOICES
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) NOT NULL,
    customer_name VARCHAR(255),
    issue_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP WITH TIME ZONE,
    subtotal NUMERIC(12, 4) NOT NULL DEFAULT 0.0000 CHECK (subtotal >= 0),
    tax_amount NUMERIC(12, 4) NOT NULL DEFAULT 0.0000 CHECK (tax_amount >= 0),
    total_amount NUMERIC(12, 4) NOT NULL DEFAULT 0.0000 CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    payment_status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
    created_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_invoice_status CHECK (payment_status IN ('UNPAID', 'PAID', 'PARTIAL', 'OVERDUE', 'CANCELLED')),
    CONSTRAINT fk_invoices_creator FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_tenant_invoice_number UNIQUE (tenant_id, invoice_number),
    CONSTRAINT uq_tenant_invoice_perimeter UNIQUE (tenant_id, invoice_id)
);

CREATE TRIGGER set_timestamp_invoices 
BEFORE UPDATE ON invoices 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 10: INVOICE_ITEMS
CREATE TABLE IF NOT EXISTS invoice_items (
    invoice_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 4) NOT NULL CHECK (unit_price >= 0),
    total_price NUMERIC(12, 4) NOT NULL CHECK (total_price >= 0),
    CONSTRAINT fk_invoice_items_invoice FOREIGN KEY (tenant_id, invoice_id) REFERENCES invoices(tenant_id, invoice_id) ON DELETE CASCADE,
    CONSTRAINT fk_invoice_items_product FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE RESTRICT
);

-- TABLE 11: GLOBAL_COMPETITORS
CREATE TABLE IF NOT EXISTS global_competitors (
    global_competitor_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_name VARCHAR(255) NOT NULL,
    website_url TEXT,
    industry_sector VARCHAR(150),
    visibility VARCHAR(10) NOT NULL DEFAULT 'GLOBAL' CHECK (visibility IN ('GLOBAL', 'PRIVATE')),
    added_by_tenant_id UUID REFERENCES companies(tenant_id) ON DELETE CASCADE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_competitor_global ON global_competitors (LOWER(competitor_name)) WHERE (visibility = 'GLOBAL');
CREATE UNIQUE INDEX IF NOT EXISTS uq_competitor_private ON global_competitors (added_by_tenant_id, LOWER(competitor_name)) WHERE (visibility = 'PRIVATE');

-- TABLE 12: TENANT_COMPETITORS
CREATE TABLE IF NOT EXISTS tenant_competitors (
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    global_competitor_id UUID NOT NULL REFERENCES global_competitors(global_competitor_id) ON DELETE CASCADE,
    custom_alias VARCHAR(255),
    is_tracked BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, global_competitor_id)
);

ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE currency_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_competitors ENABLE ROW LEVEL SECURITY;

ALTER TABLE inventory FORCE ROW LEVEL SECURITY;
ALTER TABLE currency_rates FORCE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;
ALTER TABLE invoice_items FORCE ROW LEVEL SECURITY;
ALTER TABLE global_competitors FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_competitors FORCE ROW LEVEL SECURITY;

CREATE POLICY isolation_inventory ON inventory FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_invoices ON invoices FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_invoice_items ON invoice_items FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_tenant_competitors ON tenant_competitors FOR ALL USING (tenant_id = get_current_tenant());

CREATE POLICY select_global_competitors ON global_competitors FOR SELECT 
    USING (visibility = 'GLOBAL' OR added_by_tenant_id = get_current_tenant());
CREATE POLICY write_private_competitors ON global_competitors FOR ALL 
    USING (added_by_tenant_id = get_current_tenant()) 
    WITH CHECK (added_by_tenant_id = get_current_tenant() AND visibility = 'PRIVATE');

CREATE POLICY global_read_currency ON currency_rates FOR SELECT USING (true);
CREATE POLICY system_write_currency ON currency_rates FOR ALL 
    USING (current_user = 'currency_sync_role') 
    WITH CHECK (current_user = 'currency_sync_role');
-- TABLE 13: COMPETITOR_PRODUCT_MAPPINGS
CREATE TABLE IF NOT EXISTS competitor_product_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    global_competitor_id UUID NOT NULL,
    product_id UUID NOT NULL,
    competitor_product_url TEXT,
    competitor_product_sku VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mapping_tenant_competitor FOREIGN KEY (tenant_id, global_competitor_id) REFERENCES tenant_competitors(tenant_id, global_competitor_id) ON DELETE CASCADE,
    CONSTRAINT fk_mapping_product_isolated FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_competitor_product UNIQUE (tenant_id, global_competitor_id, product_id),
    CONSTRAINT uq_tenant_mapping_perimeter UNIQUE (tenant_id, mapping_id)
);

CREATE INDEX IF NOT EXISTS idx_mappings_tenant_product ON competitor_product_mappings(tenant_id, product_id);

-- TABLE 14: COMPETITOR_PRICES
CREATE TABLE IF NOT EXISTS competitor_prices (
    competitor_price_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    mapping_id UUID NOT NULL,
    scraped_price NUMERIC(12, 4) NOT NULL CHECK (scraped_price >= 0),
    currency VARCHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_competitor_prices_mapping_isolated FOREIGN KEY (tenant_id, mapping_id) REFERENCES competitor_product_mappings(tenant_id, mapping_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_competitor_prices_mapping ON competitor_prices(tenant_id, mapping_id);
CREATE INDEX IF NOT EXISTS idx_competitor_prices_lookup ON competitor_prices(tenant_id, observed_at DESC);

-- TABLE 15: REVIEWS
CREATE TABLE IF NOT EXISTS reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    source_platform VARCHAR(50) NOT NULL, 
    reviewer_name VARCHAR(150),
    review_text TEXT NOT NULL,
    review_rating NUMERIC(3, 2) CHECK (review_rating >= 0.00 AND review_rating <= 5.00),
    review_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reviews_product_isolated FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_review_perimeter UNIQUE (tenant_id, review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_tenant_product ON reviews(tenant_id, product_id);

-- TABLE 16: SENTIMENT_RESULTS
CREATE TABLE IF NOT EXISTS sentiment_results (
    sentiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    review_id UUID NOT NULL UNIQUE,
    sentiment_score NUMERIC(5, 4) NOT NULL CHECK (sentiment_score >= -1.0000 AND sentiment_score <= 1.0000),
    sentiment_label VARCHAR(20) NOT NULL, 
    extracted_keywords JSONB DEFAULT '[]'::jsonb,
    model_version VARCHAR(50) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_sentiment_label CHECK (sentiment_label IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE')),
    CONSTRAINT fk_sentiment_review_isolated FOREIGN KEY (tenant_id, review_id) REFERENCES reviews(tenant_id, review_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sentiment_tenant_label ON sentiment_results(tenant_id, sentiment_label);

-- TABLE 17: DEMAND_FORECASTS
CREATE TABLE IF NOT EXISTS demand_forecasts (
    forecast_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    forecast_start_date DATE NOT NULL,
    forecast_end_date DATE NOT NULL,
    predicted_quantity NUMERIC(12, 2) NOT NULL CHECK (predicted_quantity >= 0),
    confidence_lower_bound NUMERIC(12, 2) CHECK (confidence_lower_bound >= 0),
    confidence_upper_bound NUMERIC(12, 2) CHECK (confidence_upper_bound >= 0), 
    model_version VARCHAR(50) NOT NULL,
    features_used JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_forecast_product_isolated FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id) ON DELETE CASCADE,
    CONSTRAINT chk_forecast_dates CHECK (forecast_end_date >= forecast_start_date),
    CONSTRAINT chk_confidence_bounds CHECK (confidence_upper_bound >= confidence_lower_bound),
    CONSTRAINT uq_tenant_forecast_perimeter UNIQUE (tenant_id, forecast_id)
);

CREATE INDEX IF NOT EXISTS idx_forecasts_lookup ON demand_forecasts(tenant_id, product_id, forecast_start_date);

-- TABLE 18: EVIDENCE_RECORDS
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    forecast_id UUID NOT NULL,
    metric_name VARCHAR(100) NOT NULL, 
    metric_value_json JSONB NOT NULL,
    contribution_weight NUMERIC(5, 4) NOT NULL CHECK (contribution_weight BETWEEN -1.0000 AND 1.0000),
    CONSTRAINT fk_evidence_forecast_isolated FOREIGN KEY (tenant_id, forecast_id) REFERENCES demand_forecasts(tenant_id, forecast_id) ON DELETE CASCADE
);

ALTER TABLE competitor_product_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE sentiment_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE demand_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE competitor_product_mappings FORCE ROW LEVEL SECURITY;
ALTER TABLE competitor_prices FORCE ROW LEVEL SECURITY;
ALTER TABLE reviews FORCE ROW LEVEL SECURITY;
ALTER TABLE sentiment_results FORCE ROW LEVEL SECURITY;
ALTER TABLE demand_forecasts FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_records FORCE ROW LEVEL SECURITY;

CREATE POLICY isolation_mappings ON competitor_product_mappings FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_competitor_prices ON competitor_prices FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_reviews ON reviews FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_sentiment ON sentiment_results FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_forecasts ON demand_forecasts FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_evidence ON evidence_records FOR ALL USING (tenant_id = get_current_tenant());
-- TABLE 19: RECOMMENDATION_OUTCOMES
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    forecast_id UUID, 
    recommended_action TEXT NOT NULL,
    expected_impact_json JSONB DEFAULT '{}'::jsonb,
    user_decision VARCHAR(30) NOT NULL DEFAULT 'PENDING', 
    actual_outcome_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_decision_state CHECK (user_decision IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT fk_rec_forecast_isolated FOREIGN KEY (tenant_id, forecast_id) REFERENCES demand_forecasts(tenant_id, forecast_id) ON DELETE RESTRICT
);

CREATE TRIGGER set_timestamp_recommendations 
BEFORE UPDATE ON recommendation_outcomes 
FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- TABLE 20: SYSTEM_ALERTS
CREATE TABLE IF NOT EXISTS system_alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL, 
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    message TEXT NOT NULL,
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_tenant_unresolved ON system_alerts(tenant_id, is_resolved) WHERE is_resolved = FALSE;

-- TABLE 21: RAG_DOCUMENTS_METADATA
CREATE TABLE IF NOT EXISTS rag_documents_metadata (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    storage_bucket_path TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    content_type VARCHAR(100),
    uploaded_by_user_id UUID,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rag_doc_user_isolated FOREIGN KEY (tenant_id, uploaded_by_user_id) REFERENCES tenant_users(tenant_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_tenant_document_perimeter UNIQUE (tenant_id, document_id)
);

-- TABLE 22: RAG_DOCUMENT_CHUNKS
CREATE TABLE IF NOT EXISTS rag_document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    document_id UUID NOT NULL,
    chunk_index INT NOT NULL CHECK (chunk_index >= 0),
    chunk_text_content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chunks_document_isolated FOREIGN KEY (tenant_id, document_id) REFERENCES rag_documents_metadata(tenant_id, document_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_chunk_index UNIQUE (tenant_id, document_id, chunk_index)
);

-- TABLE 23: DATA_SOURCES
CREATE TABLE IF NOT EXISTS data_sources (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    source_name VARCHAR(100) NOT NULL, 
    source_type VARCHAR(50) NOT NULL,  
    connection_credentials_vault TEXT, 
    sync_frequency_minutes INT DEFAULT 1440,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_source_perimeter UNIQUE (tenant_id, source_id)
);

-- TABLE 24: INGESTION_JOBS
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_id UUID NOT NULL,
    job_status VARCHAR(20) NOT NULL DEFAULT 'QUEUED', 
    rows_processed INT DEFAULT 0,
    rows_failed INT DEFAULT 0,
    error_log TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_job_status CHECK (job_status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED')),
    CONSTRAINT fk_jobs_source_isolated FOREIGN KEY (tenant_id, source_id) REFERENCES data_sources(tenant_id, source_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_job_perimeter UNIQUE (tenant_id, job_id)
);

-- TABLE 25: IMPORT_STAGING_ROWS
CREATE TABLE IF NOT EXISTS import_staging_rows (
    staging_row_id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    job_id UUID NOT NULL,
    raw_payload_json JSONB NOT NULL,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'PENDING', 
    validation_errors TEXT,
    committed_record_id UUID DEFAULT NULL,   
    committed_table TEXT DEFAULT NULL,       
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_staging_status CHECK (validation_status IN ('PENDING', 'VALID', 'INVALID', 'COMMITTED')),
    CONSTRAINT chk_committed_table_guard CHECK (committed_table IN ('products', 'inventory', 'invoices', 'invoice_items', 'reviews')),
    CONSTRAINT fk_staging_job_isolated FOREIGN KEY (tenant_id, job_id) REFERENCES ingestion_jobs(tenant_id, job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_staging_validation_lookup ON import_staging_rows(tenant_id, job_id, validation_status);

-- TABLE 26: AUDIT_LOGS
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL, 
    user_id UUID, 
    action_type VARCHAR(50) NOT NULL, 
    target_table VARCHAR(100) NOT NULL,
    record_id UUID,
    changed_data_json JSONB, 
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_compliance ON audit_logs(tenant_id, created_at DESC);

ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_documents_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_staging_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE recommendation_outcomes FORCE ROW LEVEL SECURITY;
ALTER TABLE system_alerts FORCE ROW LEVEL SECURITY;
ALTER TABLE rag_documents_metadata FORCE ROW LEVEL SECURITY;
ALTER TABLE rag_document_chunks FORCE ROW LEVEL SECURITY;
ALTER TABLE data_sources FORCE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE import_staging_rows FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY isolation_recommendations ON recommendation_outcomes FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_alerts ON system_alerts FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_rag_docs ON rag_documents_metadata FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_rag_chunks ON rag_document_chunks FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_data_sources ON data_sources FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_ingestion_jobs ON ingestion_jobs FOR ALL USING (tenant_id = get_current_tenant());
CREATE POLICY isolation_staging_rows ON import_staging_rows FOR ALL USING (tenant_id = get_current_tenant());

CREATE POLICY select_audit_logs ON audit_logs FOR SELECT USING (tenant_id = get_current_tenant());
CREATE POLICY insert_audit_logs ON audit_logs FOR INSERT WITH CHECK (tenant_id = get_current_tenant());
