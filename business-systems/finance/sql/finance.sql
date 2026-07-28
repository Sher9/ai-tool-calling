-- ============================================================
-- 财务 ERP 仿真系统：发票 / 月度营收 / 报销
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
-- 适用库：finance_db
-- ============================================================

CREATE TABLE IF NOT EXISTS fin_invoices (
    id          VARCHAR(64) PRIMARY KEY,
    invoice_no  VARCHAR(64) UNIQUE,
    supplier    VARCHAR(128) DEFAULT '',
    buyer       VARCHAR(128) DEFAULT '',
    amount      NUMERIC(14,2) DEFAULT 0,
    tax_no      VARCHAR(32)  DEFAULT '',              -- 敏感
    bank_account VARCHAR(32) DEFAULT '',              -- 敏感
    issue_date  DATE,
    status      VARCHAR(16)  DEFAULT '待付款'          -- 待付款/已付款
);
CREATE INDEX IF NOT EXISTS ix_fin_invoices_supplier ON fin_invoices(supplier);

CREATE TABLE IF NOT EXISTS fin_revenue (
    id      VARCHAR(64) PRIMARY KEY,
    month   VARCHAR(16) DEFAULT '',                   -- 2026-07
    revenue NUMERIC(14,2) DEFAULT 0,
    cost    NUMERIC(14,2) DEFAULT 0,
    profit  NUMERIC(14,2) DEFAULT 0,
    note    TEXT        DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_fin_revenue_month ON fin_revenue(month);

CREATE TABLE IF NOT EXISTS fin_expenses (
    id         VARCHAR(64) PRIMARY KEY,
    category   VARCHAR(64) DEFAULT '',                -- 差旅/办公/采购/招待
    applicant  VARCHAR(64) DEFAULT '',
    amount     NUMERIC(14,2) DEFAULT 0,
    occur_date DATE,
    status     VARCHAR(16) DEFAULT '待报销',          -- 待报销/已报销
    remark     TEXT        DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fin_expenses_category ON fin_expenses(category);

INSERT INTO fin_invoices (id, invoice_no, supplier, buyer, amount, tax_no, bank_account, issue_date, status) VALUES
    ('inv-001','FP2026070001','上海恒昇制造','我方',860000,'91310000MA1FL9X001','6222021234567890123', DATE '2026-07-05','待付款'),
    ('inv-002','FP2026070002','深圳锐驰物流','我方',540000,'91440300MA5ET2X002','6222022234567890124', DATE '2026-07-12','已付款')
ON CONFLICT (id) DO NOTHING;

INSERT INTO fin_revenue (id, month, revenue, cost, profit, note) VALUES
    ('rev-2026-06','2026-06',3200000,1900000,1300000,'Q2 收尾'),
    ('rev-2026-07','2026-07',2600000,1500000,1100000,'夏季促销')
ON CONFLICT (id) DO NOTHING;

INSERT INTO fin_expenses (id, category, applicant, amount, occur_date, status, remark) VALUES
    ('exp-001','差旅','bob',   4800, DATE '2026-07-10', '已报销', '客户拜访'),
    ('exp-002','采购','carol',12500, DATE '2026-07-15', '待报销', '研发设备'),
    ('exp-003','招待','alice',3200, DATE '2026-07-18', '待报销', '商务宴请')
ON CONFLICT (id) DO NOTHING;
