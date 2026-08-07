CREATE TABLE campaigns (
    campaign_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES companies(tenant_id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(product_id) ON DELETE SET NULL,
    campaign_brief TEXT NOT NULL,
    generated_image_key VARCHAR(512),
    status VARCHAR(50) DEFAULT 'Pending',
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_campaigns_tenant ON campaigns(tenant_id);
