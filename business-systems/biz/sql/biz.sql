-- ============================================================
-- BIZ 仿真系统：库存 / 产品参数 / 资源申请 / 报价单
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
-- 适用库：biz_db（与 Agent 平台及其它业务系统隔离）
-- ============================================================

CREATE TABLE IF NOT EXISTS inventory_items (
    sku         VARCHAR(64) PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,
    category    VARCHAR(64)  DEFAULT '',
    stock       INTEGER      DEFAULT 0,
    warehouse   VARCHAR(64)  DEFAULT '',
    price       NUMERIC(14,2) DEFAULT 0,
    updated_at  TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_inventory_items_name ON inventory_items(name);

CREATE TABLE IF NOT EXISTS product_params (
    model     VARCHAR(64) PRIMARY KEY,
    name      VARCHAR(128) NOT NULL,
    cpu       VARCHAR(64)  DEFAULT '',
    memory    VARCHAR(64)  DEFAULT '',
    disk      VARCHAR(64)  DEFAULT '',
    price     NUMERIC(14,2) DEFAULT 0,
    warranty  VARCHAR(32)  DEFAULT '',
    remark    TEXT         DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quotes (
    id         VARCHAR(64) PRIMARY KEY,
    owner      VARCHAR(64)  DEFAULT 'anonymous',
    customer   VARCHAR(128) DEFAULT '',
    total      NUMERIC(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ  DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quote_items (
    id        VARCHAR(64) PRIMARY KEY,
    quote_id  VARCHAR(64)  DEFAULT '',
    name      VARCHAR(128) DEFAULT '',
    qty       INTEGER      DEFAULT 1,
    price     NUMERIC(14,2) DEFAULT 0,
    subtotal  NUMERIC(14,2) DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_quote_items_quote_id ON quote_items(quote_id);
