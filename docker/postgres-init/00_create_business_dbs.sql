-- ============================================================
-- 为四个「仿真业务系统」创建各自独立的数据库（与 Agent 平台库 agent_platform 隔离）。
-- 仅在 Postgres 首次初始化时执行一次（数据卷持久化后不再重复）。
-- 各业务系统的建表 / 灌数据由对应服务的启动时自动完成（create_all + seed）。
-- ============================================================

SELECT 'CREATE DATABASE crm_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm_db')\gexec

SELECT 'CREATE DATABASE hr_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hr_db')\gexec

SELECT 'CREATE DATABASE finance_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'finance_db')\gexec

SELECT 'CREATE DATABASE oa_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'oa_db')\gexec

SELECT 'CREATE DATABASE biz_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'biz_db')\gexec
