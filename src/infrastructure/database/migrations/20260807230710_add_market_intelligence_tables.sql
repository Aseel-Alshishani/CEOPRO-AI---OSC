CREATE TABLE news_record (
    news_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    source_url VARCHAR(1024) NOT NULL,
    headline VARCHAR(512) NOT NULL,
    body_text TEXT,
    published_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE social_mention (
    mention_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    author_handle VARCHAR(255),
    mention_text TEXT NOT NULL,
    posted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE extracted_entity (
    entity_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    source_table VARCHAR(50) NOT NULL,
    source_record_id UUID NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_value VARCHAR(512) NOT NULL,
    confidence_score NUMERIC(4, 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_news_record_tenant ON news_record(tenant_id);
CREATE INDEX idx_social_mention_tenant ON social_mention(tenant_id);
CREATE INDEX idx_extracted_entity_tenant ON extracted_entity(tenant_id);
CREATE INDEX idx_extracted_entity_source ON extracted_entity(source_table, source_record_id);
