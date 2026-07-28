-- ============================================================
-- CRM 仿真系统：客户 / 商机
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
-- 适用库：crm_db（与 Agent 平台及其它业务系统隔离）
-- ============================================================

CREATE TABLE IF NOT EXISTS crm_customers (
    id              VARCHAR(64) PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    industry        VARCHAR(64)  DEFAULT '',
    stage           VARCHAR(32)  DEFAULT '线索',       -- 线索/商机/谈判/成交/流失
    owner           VARCHAR(64)  DEFAULT '',            -- 负责人(平台用户名)
    amount          NUMERIC(14,2) DEFAULT 0,
    contact_name    VARCHAR(64)  DEFAULT '',
    contact_phone   VARCHAR(32)  DEFAULT '',
    contact_email   VARCHAR(128) DEFAULT '',
    remark          TEXT         DEFAULT '',
    created_at      TIMESTAMPTZ  DEFAULT now(),
    updated_at      TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_crm_customers_name ON crm_customers(name);
CREATE INDEX IF NOT EXISTS ix_crm_customers_owner ON crm_customers(owner);

CREATE TABLE IF NOT EXISTS crm_deals (
    id                  VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(64) REFERENCES crm_customers(id) ON DELETE CASCADE,
    title               VARCHAR(128) DEFAULT '',
    amount              NUMERIC(14,2) DEFAULT 0,
    stage               VARCHAR(32)  DEFAULT '商机',
    expected_close_date DATE,
    owner               VARCHAR(64)  DEFAULT '',
    created_at          TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_crm_deals_customer_id ON crm_deals(customer_id);

INSERT INTO crm_customers (id, name, industry, stage, owner, amount, contact_name, contact_phone, contact_email, remark) VALUES
    ('cust-001','张三','互联网','成交','alice',1200000,'王总','13800001111','wang@yuntu.com','年度框架合同'),
    ('cust-002','李四','制造业','谈判','alice', 860000,'李经理','13900002222','li@hengsheng.com','待法务评审'),
    ('cust-003','王五','物流','商机','bob',   540000,'赵主管','13700003333','zhao@ruichi.com','初步接洽'),
    ('cust-004','赵六','传媒','线索','bob',   230000,'陈女士','13600004444','chen@xinghe.com','官网留资')
ON CONFLICT (id) DO NOTHING;

INSERT INTO crm_deals (id, customer_id, title, amount, stage, expected_close_date, owner) VALUES
    ('deal-001','cust-001','张三科技-一期采购',1200000,'成交','2026-05-30','alice'),
    ('deal-002','cust-002','李四制造-设备升级', 860000,'谈判','2026-08-15','alice'),
    ('deal-003','cust-003','王五物流-系统对接', 540000,'商机','2026-09-01','bob')
ON CONFLICT (id) DO NOTHING;
