"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # ----- App -----
    APP_NAME: str = "企业内部私有化 AI Agent 工具调度平台"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "change-me-in-production-please"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ----- Database (PostgreSQL + pg_vector) -----
    DATABASE_URL: str = "postgresql+asyncpg://postgres:123456@localhost:5432/agent_platform"
    DB_DSN_SYNC: str = "postgresql+psycopg2://postgres:123456@localhost:5432/agent_platform"

    # ----- Redis -----
    REDIS_URL: str = "redis://:123456@localhost:6379/0"

    # ----- MinIO object storage -----
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "agent-platform"
    MINIO_SECURE: bool = False

    # ----- LLM (internal / vLLM, OpenAI-compatible) -----
    # 注意：下面三个 *_BASE_URL 必须指向「真实的模型服务」，绝不是本项目后端自身（本项目默认跑在 8000，
    # 若指向 8000 会返回 404）。演示/无模型时请把 MOCK_LLM=true，无需配置这些地址。
    LLM_BASE_URL: str = ""  # 例：http://localhost:8000/v1（指你的 vLLM，端口别与本项目冲突）
    LLM_API_KEY: str = "EMPTY"
    # 私有化部署 DeepSeek 权重（如 DeepSeek-V3/V2）经 vLLM 暴露为 OpenAI 接口；
    # 若使用 DeepSeek 官方云服务，将 LLM_BASE_URL 改为 https://api.deepseek.com/v1 并填入 LLM_API_KEY
    LLM_LIGHT_MODEL: str = "deepseek-chat"
    LLM_HEAVY_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.1
    LLM_REASONING_MODEL: str = "deepseek-reasoner"

    # ----- Embedding -----
    # 留空则禁用向量召回，RAG 自动回退关键词检索（不会请求不存在的服务）。
    EMBEDDING_BASE_URL: str = ""  # 例：http://localhost:8080/v1（你的 bge embedding 服务 / TEI）
    EMBEDDING_API_KEY: str = "EMPTY"
    # 开发期使用轻量中文模型 bge-small-zh-v1.5（约 90MB / 512 维，本地 CPU/GPU 均可流畅运行）
    EMBEDDING_MODEL: str = "bge-small-zh-v1.5"
    EMBEDDING_DIM: int = 512

    # ----- Rerank (bge-reranker-v2-m3) -----
    # 留空则不重排（直接返回向量/关键词召回序）。同样不能是本项目后端。
    RERANK_BASE_URL: str = ""  # 例：http://localhost:8081
    RERANK_API_KEY: str = "EMPTY"
    RERANK_MODEL: str = "bge-reranker-v2-m3"

    # ----- Feature toggles -----
    # MOCK_LLM=true  -> run without a real LLM using a deterministic rule-based planner
    MOCK_LLM: bool = True
    # External (internet) tools are OFF by default for data-leak safety
    EXTERNAL_TOOLS_ENABLED: bool = False
    # MOCK_TOOLS=true -> 工具适配器返回仿真数据（开箱演示）。
    # 接入真实环境：在下方配置各系统地址/令牌，并将本项设为 false，
    # 未配置的系统会明确报错（不再静默返回假数据）。
    MOCK_TOOLS: bool = True

    # ----- 真实系统集成配置（填入即生效；未配置且 MOCK_TOOLS=false 时该工具报错） -----
    # 协同办公
    FEISHU_WEBHOOK_URL: str = ""          # 飞书自定义机器人 webhook
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    DOC_BASE_URL: str = ""                # 语雀/Confluence 等文档库 base url
    DOC_TOKEN: str = ""
    MAIL_SMTP_HOST: str = ""
    MAIL_SMTP_PORT: int = 465
    MAIL_IMAP_HOST: str = ""
    MAIL_IMAP_PORT: int = 993
    MAIL_USER: str = ""
    MAIL_PASSWORD: str = ""

    # 研发
    GITHUB_BASE_URL: str = "https://api.github.com"   # GitHub REST API 基地址
    GITHUB_TOKEN: str = ""                            # GitHub Personal Access Token（repo 读权限）
    SWAGGER_BASE_URL: str = ""            # Swagger/OpenAPI JSON 地址

    # 业务系统（公司自研，base url + 令牌，路径按贵司接口对齐）
    # 默认指向「仿真业务系统」的 Spring Cloud Gateway 统一网关（business-systems/，端口 8080），
    # 路径前缀分别为 /crm /hr /finance /oa，由网关路由到对应微服务。
    # 接入贵司真实系统时，把下面 URL 改成真实地址即可，令牌需与对应系统的 SERVICE_TOKEN 一致。
    CRM_BASE_URL: str = "http://localhost:8080/crm"
    CRM_TOKEN: str = "biz-svc-2026-token"
    HR_BASE_URL: str = "http://localhost:8080/hr"
    HR_TOKEN: str = "biz-svc-2026-token"
    FINANCE_BASE_URL: str = "http://localhost:8080/finance"
    FINANCE_TOKEN: str = "biz-svc-2026-token"
    OA_BASE_URL: str = "http://localhost:8080/oa"
    OA_TOKEN: str = "biz-svc-2026-token"

    # 自定义内部业务接口（统一接入 business-systems/biz 仿真服务）
    # 默认指向 biz 服务（端口 8085）；本机用 http://localhost:8085，容器内用 http://biz:8085
    BIZ_BASE_URL: str = "http://localhost:8085"
    BIZ_TOKEN: str = "biz-svc-2026-token"

    # 外网检索
    WEATHER_API_KEY: str = ""             # OpenWeatherMap key（可选，默认用 Open-Meteo 免 key）
    TAVILY_API_KEY: str = ""              # Tavily Search key（可选；配置后公开检索优先走 Tavily，质量最佳）
    SEARCH_API_KEY: str = ""              # 兼容旧字段别名（同 TAVILY_API_KEY；二者填其一即可）
    WHOIS_API_KEY: str = ""               # RDAP 免 key；商业 whois 需 key（可选）
    CALENDAR_BASE_URL: str = ""           # 已废弃：日历查询统一走 BIZ_BASE_URL 的 /calendar/events
    EXCHANGE_RATE_API_KEY: str = ""       # 实时汇率 key（可选）

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def tavily_api_key(self) -> str:
        # TAVILY_API_KEY 优先；兼容旧字段 SEARCH_API_KEY
        return (self.TAVILY_API_KEY or self.SEARCH_API_KEY or "").strip()


settings = Settings()
