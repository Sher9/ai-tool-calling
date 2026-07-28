-- ============================================================
-- 迁移脚本：补齐 RAG 知识库 / 三层记忆功能所需的库表变动
-- 适用场景：早期版本数据库（已存在 users/tools/documents/... 旧表，
--           但缺少 doc_type/trust_level/tags/version/meta/chunk_index
--           以及 episodic_memories 表）升级到当前 init.sql 结构。
-- 特性：幂等，可重复执行（已存在的列/索引/表会被跳过）。
-- 注意：向量维度默认 512（bge-small-zh-v1.5），若 EMBEDDING_DIM 不同
--       请同步修改 embedding 列维度与 ivfflat 索引的 lists 取值。
-- ============================================================

-- 1) 启用 pg_trgm（混合检索关键词召回 / 中文三元组相似度，近似 BM25）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2) documents：补齐数据治理元数据 + 版本管理字段
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='doc_type') THEN
        ALTER TABLE documents ADD COLUMN doc_type VARCHAR(32) NOT NULL DEFAULT 'general';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='trust_level') THEN
        ALTER TABLE documents ADD COLUMN trust_level VARCHAR(32) NOT NULL DEFAULT 'internal';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='source') THEN
        ALTER TABLE documents ADD COLUMN source VARCHAR(512) NOT NULL DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='tags') THEN
        ALTER TABLE documents ADD COLUMN tags JSONB NOT NULL DEFAULT '[]'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='version') THEN
        ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='doc_status') THEN
        ALTER TABLE documents ADD COLUMN doc_status VARCHAR(32) NOT NULL DEFAULT 'active';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='parent_id') THEN
        ALTER TABLE documents ADD COLUMN parent_id VARCHAR(64) REFERENCES documents (id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='created_by') THEN
        ALTER TABLE documents ADD COLUMN created_by VARCHAR(64) NOT NULL DEFAULT '';
    END IF;
END $$;

-- documents 新增索引（IF NOT EXISTS 幂等）
CREATE INDEX IF NOT EXISTS ix_documents_doc_type ON documents (doc_type);
CREATE INDEX IF NOT EXISTS ix_documents_doc_status ON documents (doc_status);

-- 3) document_chunks：补齐溯源字段与关键词/向量索引
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='document_chunks' AND column_name='chunk_index') THEN
        ALTER TABLE document_chunks ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='document_chunks' AND column_name='meta') THEN
        ALTER TABLE document_chunks ADD COLUMN meta JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;

-- document_chunks 索引（幂等）
CREATE INDEX IF NOT EXISTS ix_document_chunks_department ON document_chunks (department);
CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm
    ON document_chunks USING gin (content gin_trgm_ops);
-- 向量相似度检索（余弦），lists 约为 数据行数/1000 的近似
CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
    ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 4) 新建 episodic_memories（长期情节记忆，Agent 三层记忆 · 层级 3）
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

-- 迁移完成提示
DO $$
BEGIN
    RAISE NOTICE 'RAG 知识库 / 三层记忆迁移脚本执行完成。';
END $$;
