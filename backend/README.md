# 企业 AI Agent 工具调度平台 · 后端

企业内部私有化部署的 AI Agent 后端服务。它将大语言模型（LLM）的自然语言理解能力，与企业内部的办公协同、研发协作、业务系统（CRM / HR / 财务 ERP / OA）以及自定义内部接口连接起来，形成一个**可编排、可审计、可管控**的工具调度中枢。

- 用一句话下达任务（例如“帮我查一下本月销售数据，画个趋势图发到销售群”），Agent 自动拆分为多步工具调用并执行。
- 所有工具调用受**角色 / 部门权限**约束，敏感数据自动**脱敏**，操作全程**审计留痕**。
- 支持**零配置演示模式**（内置 mock 数据），也支持接入真实的内网系统。

---

## 技术栈

| 领域 | 选型 |
| --- | --- |
| Web 框架 | FastAPI（异步 ASGI） |
| 数据库 | PostgreSQL 16 + `pg_vector` 向量扩展（异步驱动 `asyncpg`） |
| 缓存 / 队列 | Redis |
| 对象存储 | MinIO（文档 / 附件 / 报表） |
| 大模型 | 兼容 OpenAI 接口的私有化模型（推荐 vLLM 暴露 `/v1`），如 DeepSeek |
| 向量化 | `bge-small-zh-v1.5`（512 维，本地可跑） |
| Agent 编排 | LangGraph（状态图：检索 → 规划 → 执行 → 总结） |
| 鉴权 | JWT（OAuth2 密码模式） |

---

## 目录结构

```
backend/
├── main.py                      # FastAPI 入口，启动时自动建表 + 种子数据
├── app/seed.py                  # 演示用户 / 工具注册 / 提示词模板（幂等，位于 app 包内，由 main.py 启动事件调用）
├── config.py                    # 配置（基于 pydantic-settings，读取 .env）
├── requirements.txt
├── .env.example                 # 环境变量样例
├── Dockerfile
├── sql/
│   └── init.sql                 # PostgreSQL + pg_vector 建表脚本（幂等）
└── app/
    ├── agent/                   # 层级 3：Agent 核心调度
    │   ├── llm.py               #   LLM 客户端封装（兼容 OpenAI 接口 + mock）
    │   ├── memory.py            #   会话记忆 / 用户偏好
    │   ├── rag.py               #   知识库检索 + 向量化（pg_vector）
    │   ├── planner.py           #   任务规划器（规则 / LLM function-calling）
    │   ├── executor.py          #   工具执行器（重试 / 串行·并行 / 汇总）
    │   └── graph.py             #   LangGraph 状态图编排
    ├── api/
    │   ├── deps.py              #   共享依赖（DB session、客户端 IP）
    │   └── routers/             #   路由层
    │       ├── auth.py          #   登录 / 当前用户
    │       ├── chat.py          #   对话（非流式 + SSE 流式）
    │       ├── tools.py         #   工具注册中心管理
    │       ├── admin.py         #   管理员后台（审计 / 用户 / 设置 / 统计）
    │       ├── knowledge.py     #   知识库上传与管理
    │       └── files.py         #   文件下载（MinIO 兜底）
    ├── core/                    # 横切能力
    │   ├── security.py          #   JWT 签发 / 密码哈希 / 当前用户
    │   ├── rbac.py              #   角色权限依赖
    │   ├── audit.py             #   审计日志写入
    │   ├── masking.py           #   敏感数据脱敏
    │   ├── storage.py           #   MinIO 对象存储封装
    │   ├── http.py              #   带服务令牌的异步 HTTP 客户端
    │   └── runtime_cfg.py       #   运行时开关（如外网工具总闸）
    ├── db/
    │   ├── base.py              #   异步引擎 / Session / Base
    │   └── models.py            #   ORM 模型
    ├── schemas/                 #   Pydantic 请求/响应模型
    ├── services/
    │   └── file_processing.py   #   文件解析 / 切片 / 向量化入库
    ├── tools/                   # 层级 4：工具适配层
    │   ├── base.py              #   ToolContext / ToolResult 等抽象
    │   ├── registry.py          #   工具注册与分发（含 RBAC 过滤）
    │   └── adapters/            #   各工具实现（可独立替换为真实接口）
    │       ├── office.py        #   飞书 / 邮件 / 文档 / 会议纪要
    │       ├── dev.py           #   GitHub 仓库检索 / Swagger
    │       ├── business.py      #   CRM / HR / 财务 / OA（对接 business-systems）
    │       ├── compute.py       #   沙箱 / 图表 / 汇率 / 工时成本
    │       ├── custom.py        #   库存 / 产品参数 / 资源申请 / 报价单
    │       └── external.py      #   天气 / 日历 / whois / 公开检索（默认关闭）
    └── systems/                 #   预留：外部系统对接封装
```

---

## 核心能力（分层）

后端将能力划分为若干层级，便于理解职责边界：

- **层级 3 · Agent 调度核心**：`rag`（知识检索）→ `planner`（任务规划）→ `executor`（工具执行）→ `summarize`（结果总结）。规划器自动在「单步直接调用」与「多步编排」之间切换；接入真实 LLM 时通过 function-calling 解析工具调用，演示模式则使用确定性的意图规则匹配。
- **层级 3.1 · 工具注册中心**：工具以数据库行保存（名称、描述、JSON-Schema 参数、允许角色、是否脱敏、是否需外网）。管理员可在后台可视化增删改启停，**无需改代码**即可扩展工具。
- **层级 3.2 · 知识库（RAG）**：生产级检索增强生成管线：
  - **解析**：PyMuPDF(PDF) / python-docx(Word) / openpyxl(Excel) / markdown-it-py(Markdown) 解析，并做基础清洗（去页码水印等噪声）。
  - **语义分块**：按 `doc_type` 匹配策略——`faq` 单条问答保留、`regulation`/`book` 用 `RecursiveCharacterTextSplitter`（大块 + 重叠）、`manual`/Markdown 用 `MarkdownHeaderTextSplitter` 按标题层级切分；FAQ 用自定义问答解析器，拒绝“一刀切”。
  - **混合检索**：向量召回（bge-small-zh-v1.5）+ 关键词召回（pg_trgm 相似度，近似 BM25，回退 ILIKE）并行初筛 → 元过滤（部门 / `doc_status='active'` / `doc_type`）→ 精排（bge-reranker-v2-m3 Cross-Encoder）→ **动态 Top-K**（简单问题 2–3 块，复杂推理 5–8 块）。
  - **元数据与溯源**：每个分块注入 `meta`（来源 / 页码 / 章节 / 文档类型 / 权限 / 标签 / 更新时间），生成答案时标注引用来源。
  - **版本与更新**：上传同名文档自动将旧版置 `superseded`（保留可回滚），支持 `/knowledge/{id}/rollback`；增量索引，不重建全库；管理员可调用 `/knowledge/validate` 做全量校验（重复分块 / 损坏文档）。
- **层级 3.4 · 记忆（三层架构）**：
  - **工作记忆**：单次任务推理中间态，由 Agent 状态图（`app/agent/graph.py`）在进程内承载，任务结束即清空。
  - **短期记忆**：会话（conversation）/ 消息（message）持久化（PostgreSQL），支持多轮对话与断点续聊。
  - **长期记忆**：
    - *语义记忆*：即上述 RAG 知识库（客观、稳定）。
    - *情节记忆*（`app/agent/episodic.py`）：每次对话结束由 LLM 抽取关键事实向量化存入 `episodic_memories`，下次对话语义召回并注入上下文，实现“越用越懂你”。
- **层级 3.5 · 工具执行**：按计划的串行/并行执行，含 1 次重试与失败兜底。
- **层级 4 · 工具适配**：每个适配器是 `async (args, ctx) -> ToolResult` 函数，返回文本 / 表格 / 图表 / 文件。`business.py` 通过 HTTP 调用 `business-systems` 的 Spring Cloud 网关（默认 `http://localhost:8080/{crm,hr,finance,oa}`），并透传操作人身份供行级权限判断。
- **安全合规**：JWT 鉴权、RBAC、`masking` 脱敏、`audit` 全量审计（敏感调用打标）、`runtime_cfg` 外网总闸。

---

## 快速开始

### 1. 环境准备

- Python 3.11+
- 一个运行中的 PostgreSQL 16（已启用 `vector` 扩展）+ Redis + MinIO

推荐使用仓库根目录的 `docker-compose.yml` 一键拉起依赖（PostgreSQL、Redis、MinIO 以及 `business-systems` 等业务系统）。

### 2. 安装依赖

```bash
cd backend
python -m venv .venv
.venv/Scripts/Activate.ps1        # Windows
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 按需编辑 .env（数据库、Redis、MinIO、LLM 地址、业务系统地址等）
```

### 4. 初始化数据库

```bash
# 使用 sql/init.sql 建表（脚本幂等，可重复执行）
psql "$DB_DSN_SYNC" -f sql/init.sql
```

> 应用启动（`main.py` 的 `lifespan` 事件）也会通过 SQLAlchemy 自动建表，并调用 `app/seed.py` 的 `seed_initial_data()` 幂等写入演示数据（用户、工具、提示词）。

### 5. 运行

```bash
# 开发模式
uvicorn app.main:app --reload --port 8000

# 生产模式（示例）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

API 文档：启动后访问 `http://localhost:8000/docs`（Swagger UI）。

### 6. Docker

```bash
docker build -t agent-backend .
docker run --env-file .env -p 8000:8000 agent-backend
```

---

## 配置说明（`.env` 摘要）

完整变量见 `.env.example`。关键点：

- **数据库**：`DATABASE_URL`（异步）、`DB_DSN_SYNC`（同步/种子）。
- **LLM**：`LLM_BASE_URL`（指向 vLLM 的 `/v1`）、`LLM_LIGHT_MODEL` / `LLM_HEAVY_MODEL` / `LLM_REASONING_MODEL`、`LLM_API_KEY`。
- **Embedding**：`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_DIM`（默认 512）。
- **功能开关**：
  - `MOCK_LLM`：是否用规则式规划器（无需真实模型即可跑）。
  - `MOCK_TOOLS`：工具是否返回仿真数据（开箱演示）；置 `false` 且未配置真实系统地址时，对应工具会明确报错。
  - `EXTERNAL_TOOLS_ENABLED`：外网工具总闸，默认 `false`（防止数据外泄）。
- **业务系统**：`CRM_BASE_URL` / `HR_BASE_URL` / `FINANCE_BASE_URL` / `OA_BASE_URL` 及对应 `*_TOKEN`，默认指向 `business-systems` 网关（端口 8080）。填入即生效。
- **其他真实系统**：飞书、邮件（SMTP/IMAP）、GitHub、Swagger、库存/产品/资源/报价等自研接口地址。

---

## API 概览

基础前缀 `API_V1_PREFIX`（默认 `/api/v1`）。

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 认证 | `POST /auth/login`、`GET /auth/me` | 登录获取 JWT；获取当前用户 |
| 对话 | `POST /chat` | 非流式对话，返回答案 + 步骤明细 |
|  | `POST /chat/stream` | SSE 流式对话（实时 plan + 步骤可视化） |
|  | `GET /conversations`、`GET /conversations/{id}/messages`、`DELETE /conversations/{id}` | 会话历史 |
| 工具 | `GET /tools` | 当前用户可用工具列表（按角色过滤） |
|  | `POST/PUT/DELETE /tools/...`、`POST /tools/{id}/toggle` | 管理员工具管理 |
| 知识库 | `POST /knowledge/upload`、`GET /knowledge`、`DELETE /knowledge/{id}` | 文档上传与检索（部门隔离） |
| 文件 | `GET /files/local/{key}`、`GET /files/object/{key}` | 文件下载（MinIO 兜底） |
| 管理后台 | `GET /admin/audit`、`GET /admin/audit/alerts` | 审计日志 / 敏感告警 |
|  | `GET/POST /admin/users`、`GET/PUT /admin/prompts` | 用户 / 提示词管理 |
|  | `GET/POST /admin/settings/external`、`GET /admin/stats` | 外网总闸 / 仪表盘统计 |

---

## 工具扩展

新增一个工具通常只需两步（无需改动编排逻辑）：

1. 在 `app/tools/adapters/<module>.py` 中增加一个 `async (args, ctx) -> ToolResult` 函数，并在模块 `ADAPTERS` 字典注册。
2. 通过后台 `POST /tools` 或编辑 `app/seed.py` 的 `TOOLS` 元组写入一条 `Tool` 记录（`adapter` 字段指向注册 key，并配置 `parameters` JSON-Schema、`allowed_roles`、`mask_sensitive` 等）；重启服务后由启动事件幂等写入。

规划器（`planner.py`）在演示模式下通过关键词规则匹配工具；接入真实 LLM（`MOCK_LLM=false`）时，会基于 `build_function_schemas` 生成的 JSON-Schema 进行 function-calling 规划。

---

## 安全与合规

- **鉴权**：所有 API 需携带 `Authorization: Bearer <JWT>`。
- **RBAC**：每个工具可配置 `allowed_roles`，列表为空表示全员可用；业务系统侧再做行级隔离（如 CRM 仅查本人客户）。
- **脱敏**：标记为 `mask_sensitive` 的工具输出（手机号、税号、银行账号等）经 `core/masking.py` 统一脱敏。
- **审计**：每次登录、工具调用、管理员操作都写入 `audit_logs`；触达敏感数据的调用标记 `sensitive=true`，可在后台告警查看。
- **外网管控**：`external` 类工具默认关闭，由 `EXTERNAL_TOOLS_ENABLED` 及后台开关统一管控。

---

## 默认演示账号（来自 `app/seed.py`）

| 用户名 | 密码 | 角色 | 部门 |
| --- | --- | --- | --- |
| `admin` | `admin123` | admin | general |
| `alice` | `alice123` | sales | sales |
| `bob` | `bob123` | sales | sales |
| `carol` | `carol123` | tech | tech |
| `dave` | `dave123` | finance | finance |
| `erin` | `erin123` | hr | hr |

> 生产环境请务必修改默认密码与 `SECRET_KEY`，并将 `MOCK_*` 调整为对接真实系统的配置。

---

## 与其他模块的关系

- **Frontend（前端）**：仓库 `frontend/` 提供对话与管理界面，调用本后端 API。
- **Business Systems（业务系统）**：仓库 `business-systems/` 是 Spring Cloud 微服务（CRM / HR / 财务 / OA），默认作为本平台业务类工具的真实后端；HTTP 调用经网关并透传操作人身份。
- **根目录 `docker-compose.yml`**：编排后端依赖（PostgreSQL / Redis / MinIO）以及业务系统，便于一体化部署。
