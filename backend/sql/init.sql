-- ============================================================
-- 企业内部私有化 AI Agent 工具调度平台 - 数据库初始化脚本
-- 适用于 PostgreSQL 16 + pg_vector 扩展（docker 镜像 pgvector/pgvector:pg16）
-- 说明：
--   1) 脚本使用 CREATE TABLE IF NOT EXISTS，可重复执行（幂等）；
--   2) 向量维度默认 512（与 config.EMBEDDING_DIM=bge-small-zh-v1.5 对应），
--      若更换 embedding 模型请同步修改 document_chunks.embedding 维度与 ivfflat 索引；
--   3) 仅建表与索引，演示数据由后端 seed.py 自动写入，避免重复灌库。
-- ============================================================

-- 启用向量扩展（RAG 检索依赖）
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- RBAC: 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(64)  PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    display_name  VARCHAR(128) NOT NULL DEFAULT '',
    password_hash VARCHAR(128) NOT NULL DEFAULT '',
    role          VARCHAR(32)  NOT NULL DEFAULT 'employee',  -- admin/employee/finance/tech/sales/hr
    department    VARCHAR(64)  NOT NULL DEFAULT 'general',   -- general/tech/sales/finance/hr
    disabled      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

-- ---------------------------------------------------------------------------
-- 工具注册中心（层级 3.1）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tools (
    id               VARCHAR(64)  PRIMARY KEY,
    name             VARCHAR(128) NOT NULL UNIQUE,            -- 供 LLM function-calling 使用的技术名
    display_name     VARCHAR(128) NOT NULL DEFAULT '',
    category         VARCHAR(64)  NOT NULL DEFAULT 'office',  -- office/dev/business/compute/custom/external
    description      TEXT         NOT NULL DEFAULT '',
    adapter          VARCHAR(128) NOT NULL DEFAULT '',         -- 对应 tools/adapters 实现 key
    parameters       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    allowed_roles    JSONB        NOT NULL DEFAULT '[]'::jsonb,-- 空数组表示全员可用
    enabled          BOOLEAN      NOT NULL DEFAULT TRUE,
    mask_sensitive   BOOLEAN      NOT NULL DEFAULT TRUE,       -- 输出是否过数据脱敏
    requires_internet BOOLEAN     NOT NULL DEFAULT FALSE,      -- 是否需外网（受开关管控）
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tools_name ON tools (name);

-- ---------------------------------------------------------------------------
-- 记忆：会话与消息（层级 3.4）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id         VARCHAR(64)  PRIMARY KEY,
    user_id    VARCHAR(64)  REFERENCES users (id) ON DELETE CASCADE,
    title      VARCHAR(256) NOT NULL DEFAULT '新对话',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id);

CREATE TABLE IF NOT EXISTS messages (
    id              VARCHAR(64)  PRIMARY KEY,
    conversation_id VARCHAR(64)  REFERENCES conversations (id) ON DELETE CASCADE,
    role            VARCHAR(16)  NOT NULL,                    -- user / assistant / system
    content         TEXT         NOT NULL DEFAULT '',
    meta            JSONB        NOT NULL DEFAULT '{}'::jsonb, -- 工具调用/结果等结构化数据
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id);

-- ---------------------------------------------------------------------------
-- 操作审计日志（层级 3 / 安全合规）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id         VARCHAR(64)  PRIMARY KEY,
    user_id    VARCHAR(64)  NOT NULL DEFAULT '',
    username   VARCHAR(64)  NOT NULL DEFAULT '',
    action     VARCHAR(64)  NOT NULL,                         -- tool_call / login / admin_op / sensitive_alert
    resource   VARCHAR(256) NOT NULL DEFAULT '',
    detail     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ip         VARCHAR(64)  NOT NULL DEFAULT '',
    sensitive  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);

-- ---------------------------------------------------------------------------
-- 多步骤任务执行记录
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_records (
    id              VARCHAR(64)  PRIMARY KEY,
    conversation_id VARCHAR(64)  NOT NULL DEFAULT '',
    user_id         VARCHAR(64)  NOT NULL DEFAULT '',
    title           VARCHAR(256) NOT NULL DEFAULT '',
    plan            JSONB        NOT NULL DEFAULT '{}'::jsonb, -- 步骤 + 结果
    status          VARCHAR(32)  NOT NULL DEFAULT 'success',  -- success/failed/partial
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_task_records_conversation_id ON task_records (conversation_id);
CREATE INDEX IF NOT EXISTS ix_task_records_user_id ON task_records (user_id);

-- ---------------------------------------------------------------------------
-- 知识库（RAG，层级 3.2）+ pg_vector
-- ---------------------------------------------------------------------------
-- 倒排 / 关键词检索依赖（混合检索初筛层：BM25 近似 + 中文三元组相似度）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS documents (
    id          VARCHAR(64)  PRIMARY KEY,
    title       VARCHAR(256) NOT NULL,
    department  VARCHAR(64)  NOT NULL DEFAULT 'general',      -- 知识库按部门隔离
    file_path   VARCHAR(512) NOT NULL DEFAULT '',             -- MinIO 对象 key

    -- 数据治理 / 元数据
    doc_type    VARCHAR(32)  NOT NULL DEFAULT 'general',      -- faq/regulation/manual/book/general
    trust_level VARCHAR(32)  NOT NULL DEFAULT 'internal',      -- official/internal/external
    source      VARCHAR(512) NOT NULL DEFAULT '',             -- 文档来源 / 出处 URL
    tags        JSONB         NOT NULL DEFAULT '[]',          -- 业务标签

    -- 版本管理
    version     INTEGER       NOT NULL DEFAULT 1,
    doc_status  VARCHAR(32)  NOT NULL DEFAULT 'active',       -- active/expired/superseded
    parent_id   VARCHAR(64)  REFERENCES documents (id) ON DELETE SET NULL,

    -- 索引状态
    chunk_count INTEGER       NOT NULL DEFAULT 0,
    status      VARCHAR(32)  NOT NULL DEFAULT 'indexed',      -- indexed/failed
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_by  VARCHAR(64)  NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_documents_doc_type ON documents (doc_type);
CREATE INDEX IF NOT EXISTS ix_documents_doc_status ON documents (doc_status);

CREATE TABLE IF NOT EXISTS document_chunks (
    id           VARCHAR(64)  PRIMARY KEY,
    document_id  VARCHAR(64)  REFERENCES documents (id) ON DELETE CASCADE,
    department   VARCHAR(64)  NOT NULL DEFAULT 'general',
    content      TEXT         NOT NULL,
    embedding    VECTOR(512),                                -- 维度与 EMBEDDING_DIM 保持一致
    chunk_index  INTEGER       NOT NULL DEFAULT 0,
    meta         JSONB         NOT NULL DEFAULT '{}'         -- 溯源：source/title/page/section/doc_type/permission/tags/updated_at
);
CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS ix_document_chunks_department ON document_chunks (department);
-- 关键词召回（中文三元组相似度，近似 BM25）
CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm ON document_chunks USING gin (content gin_trgm_ops);
-- 向量相似度检索索引（余弦距离），lists 取值约为 数据行数/1000 的近似
CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
    ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- 长期情节记忆（Agent 记忆机制 · 层级 3）：跨会话沉淀关键事实
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS episodic_memories (
    id          VARCHAR(64)  PRIMARY KEY,
    user_id     VARCHAR(64)  NOT NULL,
    department  VARCHAR(64)  NOT NULL DEFAULT 'general',
    content     TEXT         NOT NULL,
    category    VARCHAR(32)  NOT NULL DEFAULT 'fact',        -- fact/preference/event
    embedding   VECTOR(512),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_episodic_memories_user_id ON episodic_memories (user_id);
CREATE INDEX IF NOT EXISTS ix_episodic_memories_department ON episodic_memories (department);
CREATE INDEX IF NOT EXISTS ix_episodic_memories_embedding
    ON episodic_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ---------------------------------------------------------------------------
-- Prompt 模板管理（层级 3.6）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompts (
    id         VARCHAR(64)  PRIMARY KEY,
    key        VARCHAR(128) NOT NULL UNIQUE,
    title      VARCHAR(128) NOT NULL DEFAULT '',
    content    TEXT         NOT NULL,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompts_key ON prompts (key);
