
-- 1. SYSTEM EXTENSIONS & CORE FOUNDATION
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;



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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);



-- TABLE 2: USERS (Global Centralized Authentication Directory)

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150),
    preferred_language VARCHAR(5) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Compliance Constraint: Enforces global standard email patterns at db-level
    CONSTRAINT chk_email_format CHECK (email ~* '^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}$')
);



-- TABLE 3: TENANT_USERS (Pivot Table for RBAC Authorization Loops)

CREATE TABLE tenant_users (
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'staff', -- Validated roles: owner, admin, manager, accountant, staff
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);



-- TABLE 4: PRODUCTS (Dynamic Multilingual Catalog Layer)

CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_name JSONB NOT NULL, -- Format: {"en": "iPhone 15", "ar": "آيفون ١٥"}
    brand JSONB,
    category JSONB,
    description JSONB, -- Context rich text used to extract semantic AI embeddings
    current_price NUMERIC(10, 2) NOT NULL CHECK (current_price >= 0),
    currency VARCHAR(3) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    metadata JSONB DEFAULT '{}'::jsonb, -- Flexible schema-less properties for developer agility
    created_by_user_id UUID,
    updated_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE, -- Soft delete management for GDPR asset tracking
    CONSTRAINT chk_product_source CHECK (source IN ('MANUAL', 'IMPORTED')),
    CONSTRAINT fk_products_creator FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES tenant_users(tenant_id, user_id),
    CONSTRAINT fk_products_updater FOREIGN KEY (tenant_id, updated_by_user_id) REFERENCES tenant_users(tenant_id, user_id)
);



-- TABLE 5: PRODUCT_PRICE_HISTORY (Internal Financial Price Fluctuations)

CREATE TABLE product_price_history (
    price_history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    old_price NUMERIC(10, 2) CHECK (old_price >= 0),
    new_price NUMERIC(10, 2) NOT NULL CHECK (new_price >= 0),
    currency VARCHAR(3) NOT NULL,
    changed_by_user_id UUID,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_price_history_user FOREIGN KEY (tenant_id, changed_by_user_id) REFERENCES tenant_users(tenant_id, user_id)
);


-- TABLE 6: INVENTORY (Warehouse Allocations & Safety Reorder Thresholds)

CREATE TABLE inventory (
    inventory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reorder_level INT DEFAULT 10 CHECK (reorder_level >= 0),
    updated_by_user_id UUID,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_inventory_tenant_product UNIQUE (tenant_id, product_id),
    CONSTRAINT fk_inventory_user FOREIGN KEY (tenant_id, updated_by_user_id) REFERENCES tenant_users(tenant_id, user_id)
);




-- TABLE 7: CURRENCY_RATES (Global Multilateral Exchange Rate Directory)

CREATE TABLE currency_rates (
    rate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_currency VARCHAR(3) NOT NULL,
    target_currency VARCHAR(3) NOT NULL,
    rate NUMERIC(18, 8) NOT NULL CHECK (rate > 0),
    rate_date TIMESTAMP WITH TIME ZONE NOT NULL, -- Safeguards volatile conversion periods
    source VARCHAR(100),
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_currency_rate_time UNIQUE (base_currency, target_currency, rate_date)
);



-- TABLE 8: INVOICES (Sales Master Document Headers)

CREATE TABLE invoices (
    invoice_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) NOT NULL, -- Unique incremental identifier within each tenant scope
    payment_method VARCHAR(50) NOT NULL,  -- Standard options: CASH, CREDIT_CARD, APPLE_PAY
    sub_total NUMERIC(12, 2) NOT NULL CHECK (sub_total >= 0),
    tax_amount NUMERIC(12, 2) NOT NULL CHECK (tax_amount >= 0),
    discount_amount NUMERIC(12, 2) DEFAULT 0.00 CHECK (discount_amount >= 0),
    grand_total NUMERIC(12, 2) NOT NULL CHECK (grand_total >= 0),
    currency VARCHAR(3) NOT NULL,
    sale_source VARCHAR(50) DEFAULT 'POS', -- Point of Sale vs E-Commerce channels
    issued_by_user_id UUID,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_invoice_per_tenant UNIQUE (tenant_id, invoice_number),
    CONSTRAINT fk_invoices_user FOREIGN KEY (tenant_id, issued_by_user_id) REFERENCES tenant_users(tenant_id, user_id)
);




-- TABLE 9: INVOICE_ITEMS (Granular Sales Document Line Details)

CREATE TABLE invoice_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id UUID NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0), -- Captured price lock at point of purchase
    total_price NUMERIC(10, 2) NOT NULL CHECK (total_price >= 0),
    CONSTRAINT chk_item_total CHECK (total_price = (quantity * unit_price))
);



-- TABLE 10: GLOBAL_COMPETITORS (Canonical Marketplace Directory Registry)

CREATE TABLE global_competitors (
    competitor_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competitor_name VARCHAR(255) UNIQUE NOT NULL, -- Clean master record prevents duplicate spellings
    country_code VARCHAR(2),
    website_url VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);




-- TABLE 11: TENANT_COMPETITORS (Workspace Specific Target Focus Configurations)

CREATE TABLE tenant_competitors (
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL REFERENCES global_competitors(competitor_id) ON DELETE CASCADE,
    relevance_score INT DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
    market_activity_level VARCHAR(50),
    source VARCHAR(20) NOT NULL DEFAULT 'SYSTEM_DISCOVERED',
    added_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, competitor_id),
    CONSTRAINT fk_tenant_competitors_user FOREIGN KEY (tenant_id, added_by_user_id) REFERENCES tenant_users(tenant_id, user_id),
    CONSTRAINT chk_competitor_source CHECK (source IN ('MANUAL', 'SYSTEM_DISCOVERED'))
);



-- TABLE 12: COMPETITOR_PRODUCT_MAPPINGS (High Efficiency URL Resource Indexes)

CREATE TABLE competitor_product_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL,
    competitor_product_url TEXT NOT NULL, -- Static path targeting directly for iterative scrapes
    product_name_captured VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mappings_tenant_comp FOREIGN KEY (tenant_id, competitor_id) REFERENCES tenant_competitors(tenant_id, competitor_id) ON DELETE CASCADE,
    CONSTRAINT uq_tenant_product_competitor UNIQUE (tenant_id, product_id, competitor_id)
);




-- TABLE 13: COMPETITOR_PRICES (High Performance Numerical Delta Tracker)

CREATE TABLE competitor_prices (
    price_entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    mapping_id UUID NOT NULL REFERENCES competitor_product_mappings(mapping_id) ON DELETE CASCADE,
    price_found NUMERIC(10, 2) NOT NULL CHECK (price_found >= 0),
    currency VARCHAR(3) NOT NULL,
    collection_method VARCHAR(50) NOT NULL DEFAULT 'WEB_SCRAPER',
    captured_by_user_id UUID,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_prices_tenant_user FOREIGN KEY (tenant_id, captured_by_user_id) REFERENCES tenant_users(tenant_id, user_id),
    CONSTRAINT chk_price_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED', 'WEB_SCRAPER'))
);



-- TABLE 14: REVIEWS (Multi-Source Index Supporting Dense Semantic Vectors)

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
    review_vector vector(1536), -- Accommodates open-source or commercial embedding models
    embedding_model_version VARCHAR(50) DEFAULT 'text-embedding-3-small', -- Mitigates model drift mismatch risks
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_review_subject_type CHECK (subject_type IN ('PRODUCT', 'COMPETITOR', 'BUSINESS')),
    CONSTRAINT chk_review_collection_method CHECK (collection_method IN ('MANUAL', 'PUBLIC_API', 'PUBLIC_FEED')),
    CONSTRAINT chk_review_source_status CHECK (source_status IN ('ALLOWED', 'RESTRICTED', 'BLOCKED')),
    CONSTRAINT fk_reviews_tenant_comp FOREIGN KEY (tenant_id, competitor_id) REFERENCES tenant_competitors(tenant_id, competitor_id) ON DELETE CASCADE
);



-- TABLE 15: SENTIMENT_RESULTS (Model Classification Probabilities Matrix)

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



-- TABLE 16: DEMAND_FORECASTS (XGBoost Future Demand Expectations Logs)

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




-- TABLE 17: EVIDENCE_RECORDS (Unified AI Reasoning & Business Assertions Log)

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



-- TABLE 18: RECOMMENDATION_OUTCOMES (Closed-Loop Model Evaluation Tracer)

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




-- TABLE 19: RAG_DOCUMENTS_METADATA (Physical File Pointer Manifests)

CREATE TABLE rag_documents_metadata (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    minio_object_key VARCHAR(512) NOT NULL,
    processed_status VARCHAR(50) DEFAULT 'Pending',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);



-- TABLE 20: RAG_DOCUMENT_CHUNKS (Contextual Text Splitting & Embedding Depot)

CREATE TABLE rag_document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES rag_documents_metadata(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024), -- Built to host highly accurate multi-lingual dense models
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- TABLE 21: DATA_SOURCES (Collection Compliance Policy Boundaries Engine)

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



-- TABLE 22: INGESTION_JOBS (Pipeline Synchronization Execution Runs)

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



-- TABLE 23: IMPORT_STAGING_ROWS (Intermediate Data Validation Sandbox)

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

