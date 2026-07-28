-- ============================================================
-- OA 仿真系统：审批单 / 审批节点
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
-- 适用库：oa_db
-- ============================================================

CREATE TABLE IF NOT EXISTS oa_approvals (
    id           VARCHAR(64) PRIMARY KEY,
    type         VARCHAR(32) DEFAULT '',              -- 请假/出差/报销/采购
    applicant    VARCHAR(64) DEFAULT '',
    title        VARCHAR(128) DEFAULT '',
    content      TEXT        DEFAULT '',
    status       VARCHAR(16) DEFAULT '审批中',         -- 审批中/已通过/已驳回
    current_node VARCHAR(32) DEFAULT '',              -- 当前待审批节点名
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_oa_approvals_applicant ON oa_approvals(applicant);

CREATE TABLE IF NOT EXISTS oa_approval_nodes (
    id          VARCHAR(64) PRIMARY KEY,
    approval_id VARCHAR(64) REFERENCES oa_approvals(id) ON DELETE CASCADE,
    node_name   VARCHAR(32) DEFAULT '',               -- 部门主管/财务/人事/总经理
    seq         INTEGER     DEFAULT 0,
    approver    VARCHAR(64) DEFAULT '',               -- 应审批人(平台用户名)
    status      VARCHAR(16) DEFAULT '待审批',          -- 待审批/已通过/已驳回
    acted_at    TIMESTAMPTZ,
    comment     TEXT        DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_oa_approval_nodes_approval_id ON oa_approval_nodes(approval_id);

INSERT INTO oa_approvals (id, type, applicant, title, content, status, current_node) VALUES
    ('oa-seed-001','请假','bob','Bob 年假申请','申请 8/1-8/3 年假 3 天','审批中','部门主管'),
    ('oa-seed-002','报销','carol','Carol 设备采购报销','研发设备报销 12500 元','已通过','')
ON CONFLICT (id) DO NOTHING;

INSERT INTO oa_approval_nodes (id, approval_id, node_name, seq, approver, status) VALUES
    ('oa-seed-001-n1','oa-seed-001','部门主管',1,'admin','待审批'),
    ('oa-seed-001-n2','oa-seed-001','人事',2,'erin','待审批'),
    ('oa-seed-002-n1','oa-seed-002','部门主管',1,'admin','已通过'),
    ('oa-seed-002-n2','oa-seed-002','财务',2,'dave','已通过')
ON CONFLICT (id) DO NOTHING;
