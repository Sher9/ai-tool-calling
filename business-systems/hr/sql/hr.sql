-- ============================================================
-- HR 仿真系统：员工 / 考勤 / 假期
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT ... ON CONFLICT DO NOTHING
-- 适用库：hr_db
-- ============================================================

CREATE TABLE IF NOT EXISTS hr_employees (
    id           VARCHAR(64) PRIMARY KEY,
    employee_no  VARCHAR(32)  UNIQUE,
    username     VARCHAR(64)  UNIQUE,                  -- 关联平台账号
    name         VARCHAR(64)  DEFAULT '',
    department   VARCHAR(64)  DEFAULT '',
    position     VARCHAR(64)  DEFAULT '',
    manager      VARCHAR(64)  DEFAULT '',              -- 直属上级(平台用户名)
    hire_date    DATE,
    status       VARCHAR(16)  DEFAULT '在职',          -- 在职/离职
    leave_balance INTEGER     DEFAULT 0,               -- 剩余年假(天)
    id_card      VARCHAR(32)  DEFAULT '',              -- 敏感
    salary       NUMERIC(12,2) DEFAULT 0,              -- 敏感
    created_at   TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_hr_employees_username ON hr_employees(username);

CREATE TABLE IF NOT EXISTS hr_attendance (
    id         VARCHAR(64) PRIMARY KEY,
    employee_id VARCHAR(64) REFERENCES hr_employees(id) ON DELETE CASCADE,
    work_date  DATE,
    check_in   VARCHAR(8) DEFAULT '',                  -- 09:05
    check_out  VARCHAR(8) DEFAULT '',
    status     VARCHAR(16) DEFAULT '正常'              -- 正常/迟到/缺勤/请假
);
CREATE INDEX IF NOT EXISTS ix_hr_attendance_employee_id ON hr_attendance(employee_id);
CREATE INDEX IF NOT EXISTS ix_hr_attendance_work_date ON hr_attendance(work_date);

CREATE TABLE IF NOT EXISTS hr_leaves (
    id         VARCHAR(64) PRIMARY KEY,
    employee_id VARCHAR(64) REFERENCES hr_employees(id) ON DELETE CASCADE,
    type       VARCHAR(32) DEFAULT '年假',             -- 年假/事假/病假
    start_date DATE,
    end_date   DATE,
    days       INTEGER     DEFAULT 0,
    reason     TEXT        DEFAULT '',
    status     VARCHAR(16) DEFAULT '审批中',          -- 审批中/已通过/已驳回
    approver   VARCHAR(64) DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_hr_leaves_employee_id ON hr_leaves(employee_id);

INSERT INTO hr_employees (id, employee_no, username, name, department, position, manager, hire_date, status, leave_balance, id_card, salary) VALUES
    ('emp-001','E0001','admin','管理员','总经办','平台管理员','',     DATE '2023-01-01', '在职', 15, '110101199001011234', 40000),
    ('emp-002','E0002','alice','Alice','销售部','销售经理','admin', DATE '2023-03-15', '在职', 10, '310101199205062345', 22000),
    ('emp-003','E0003','bob',  'Bob',  '销售部','销售代表','alice', DATE '2023-06-01', '在职',  8, '440101199308153456', 15000),
    ('emp-004','E0004','carol','Carol','研发部','研发主管','admin', DATE '2022-09-01', '在职', 12, '510101199010204567', 28000),
    ('emp-005','E0005','dave', 'Dave', '财务部','财务专员','admin', DATE '2022-11-01', '在职',  9, '320101199112055678', 18000),
    ('emp-006','E0006','erin', 'Erin', '人事部','人事专员','admin', DATE '2023-02-01', '在职', 11, '120101199203106789', 16000)
ON CONFLICT (id) DO NOTHING;

INSERT INTO hr_attendance (id, employee_id, work_date, check_in, check_out, status) VALUES
    ('att-001','emp-001', DATE '2026-07-01', '09:01','18:30','正常'),
    ('att-002','emp-001', DATE '2026-07-02', '09:02','18:30','正常'),
    ('att-003','emp-001', DATE '2026-07-03', '09:00','18:30','正常'),
    ('att-004','emp-002', DATE '2026-07-01', '09:05','18:30','正常'),
    ('att-005','emp-002', DATE '2026-07-02', '09:03','18:30','正常'),
    ('att-006','emp-003', DATE '2026-07-01', '09:20','18:30','迟到')
ON CONFLICT (id) DO NOTHING;

INSERT INTO hr_leaves (id, employee_id, type, start_date, end_date, days, reason, status, approver) VALUES
    ('lv-001','emp-003','年假', DATE '2026-08-01', DATE '2026-08-03', 3, '回家探亲', '已通过', 'alice'),
    ('lv-002','emp-002','事假', DATE '2026-07-25', DATE '2026-07-25', 1, '病假', '审批中', '')
ON CONFLICT (id) DO NOTHING;
