# 企业内部私有化 AI Agent 工具调度平台

全公司员工通用的自然语言办公助手：通过对话自动调用各类内部系统、文件处理、数据查询工具，自动完成多步骤复杂办公任务。**全内网私有化部署，业务数据不外流**，具备完整权限隔离、操作审计、数据脱敏能力。

> 本仓库是一个**可运行的 MVP**：后端核心（FastAPI + LangGraph）完整实现，各类内部系统（飞书 / GitHub / CRM / HR / 财务 / OA …）以**适配器 + Mock 数据**形式接入，开箱即用、无需真实第三方账号。接入真实系统只需改写对应 `backend/app/tools/adapters/*.py` 的函数体。

---

## 一、五层架构对应

| 层级 | 本仓库实现 |
|---|---|
| **层级 1 前端交互层** | `frontend/` Vue3 + Element Plus：对话窗口（多轮上下文 + 任务执行步骤可视化 + 工具结果表格/图表展示）、知识库上传、个人中心、管理员后台（工具管理 / 角色权限 / 审计日志 / 外网开关 / 提示词配置） |
| **层级 3 Agent 核心调度服务** | `backend/app/agent/`：工具注册中心、RAG 增强、Planner（单工具 / 多步骤自动切换）、记忆管理（Redis 短期 + 长期偏好）、工具执行器（重试 / 熔断 / 格式化）、LangGraph 编排、私有化大模型调度服务 |
| **层级 4 工具适配微服务层** | `backend/app/tools/adapters/`：通用 / 办公 / 研发 / Git 效能 / 业务 / 计算可视化 / 自定义 / 外网 / 知识库 九类适配器，统一封装外部接口 |
| **层级 5 数据持久存储层** | PostgreSQL + `pg_vector`（业务数据 + 向量库合一）、Redis（会话缓存 / 限流 / 长期记忆）、MinIO（文档 / 报表 / 截图） |
| **层级 2/3 之间** | 统一 Function Calling 规范（JSON-Schema 入参出参），后台可视化配置即可新增工具，无需改代码 |

---

## 二、能力清单（均已实现调度链路）

- **通用基础（全员）**：当前时间 / 时区、数学表达式计算、文本相似度对比
- **协同办公（全员）**：飞书消息、企业邮件收发 / 解析 / 周报、在线文档检索 / 新建 / 编辑、会议纪要提取
- **研发（技术部专属，角色隔离）**：GitHub 仓库检索（搜仓库 / 列分支）、Swagger 接口解析、Git 提交周报生成
- **企业知识库 RAG（按部门隔离）**：向量语义检索
- **业务系统（分部门隔离）**：CRM（行权限：仅看自己客户）、HR（仅看本人）、财务 ERP（仅财务岗）、OA 审批发起 / 进度
- **计算 & 可视化**：折线 / 柱状 / Mermaid 流程图、汇率 / 工时成本换算
- **自定义内部业务**：库存查询、产品参数、客户报价单
- **外网检索（默认关闭，管理员按需开启）**：天气、日历、域名 / IP、公开资料

**安全能力**：RBAC 角色权限、部门 / 行级数据隔离、全流程操作审计、敏感操作告警面板、数据脱敏（手机号 / 邮箱 / 身份证 / 银行卡 / 薪资）、外网工具全局开关、私有化部署（数据不出服务器）。

---

## 三、快速开始

### 方式 A：Docker Compose（推荐，一条命令）

```bash
# 首次运行需准备后端环境变量（compose 通过 backend/.env 注入）
cp backend/.env.example backend/.env
docker compose up --build
```

- 后端： http://localhost:8000 （OpenAPI 文档 `/docs`）
- 前端： http://localhost:5173
- 本地 Embedding 服务： http://localhost:8088 （bge-small-zh-v1.5，`/v1/embeddings`）
- 本地 Rerank 服务： http://localhost:8089 （bge-reranker-v2-m3，`/rerank`）
- MinIO 控制台： http://localhost:9001 （minioadmin / minioadmin）
- PostgreSQL 已含 `pg_vector` 扩展（镜像 `pgvector/pgvector:pg16`）

### 方式 B：本地分服务运行

前置：Python 3.11+、Node 20+、本地 PostgreSQL(含 pgvector) / Redis / MinIO。

```bash
# 1) 后端
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # 按需修改数据库连接
uvicorn app.main:app --reload --port 8000

# 2) 本地 Embedding 服务（bge-small-zh-v1.5，开启向量召回需要它）
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r embedding_service/requirements.txt
python -m embedding_service        # 监听 0.0.0.0:8088，首次运行自动下载模型

# 2.5) 本地 Rerank 服务（bge-reranker-v2-m3，开启精排需要它）
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r rerank_service/requirements.txt
python -m rerank_service           # 监听 0.0.0.0:8089，首次运行自动下载模型

# 3) 前端（另开终端）
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

> `.env` 中 `EMBEDDING_BASE_URL` 已默认指向 `http://localhost:8088/v1`（本地 embedding 服务）。
> 若暂时不启动该服务，把 `EMBEDDING_BASE_URL` 留空即可，RAG 自动回退关键词检索（仍可运行，只是无向量语义召回）。

**获取 bge-small-zh-v1.5 权重**（服务首次启动会自动从 HF 镜像下载；若运行环境无法访问外网，请预置本地权重）：
```bash
# 在可联网机器执行，把权重下到本地目录：
pip install -U "huggingface_hub[cli]"
hf download BAAI/bge-small-zh-v1.5 --local-dir ./bge-small-zh-v1.5
# 拷到本项目：backend/data/models/BAAI/bge-small-zh-v1.5/ ，重启 embedding 服务即生效
# 国内镜像可在 embedding 服务启动前设置：set HF_ENDPOINT=https://hf-mirror.com
```

> 默认 `MOCK_LLM=true`：无需真实大模型即可运行（Planner 使用确定性规则引擎）。接入真实模型时把 `.env` 中 `MOCK_LLM=false` 并填好 `LLM_BASE_URL`（指向内网 vLLM，OpenAI 兼容接口）。

### 演示账号（启动后自动 seed）

| 账号 | 密码 | 角色 |
|---|---|---|
| `admin` | `admin123` | 管理员 |
| `alice` | `alice123` | 销售 |
| `carol` | `carol123` | 研发 |
| `dave` | `dave123` | 财务 |
| `erin` | `erin123` | 人事 |

---

## 四、试试这些自然语言指令

- **多步骤**：`统计本月销售数据→生成 Excel 趋势图→发送销售群→写入周报文档`
- **研发**：`帮我 review 一下 MR 128` / `检索 order 相关代码片段` / `生成本周 Git 提交周报`
- **业务（行权限）**：用 `alice` 登录后 `查一下我的客户`（只能看到自己的客户）
- **脱敏验证**：用 `dave` 登录 `查询本月发票`（银行卡 / 税号被自动脱敏）
- **计算**：`生成一张本月销售 Mermaid 流程图` / `算一下 (1+2)*3/sqrt(9) 等于多少`
- **知识库 RAG**：`知识库里关于退款流程是怎么规定的` → `vector_search` 检索片段并引用
- **外网**：管理员后台「系统设置」开启外网工具后，`北京今天天气怎么样`

前端会以**步骤时间线**实时展示 Planner 拆解出的每一步工具调用与返回结果（表格 / 图表 / 文本）。

---

## 五、功能点与工具调用详解（完整清单）

平台当前内置 **35 个工具**，分 8 大类。工具统一遵循 Function Calling 规范（入参出参 JSON-Schema），由 Agent 的 Planner 根据自然语言自动选择调用，或由管理员在后台统一启停 / 配置可见角色。

> 说明：当前为 MVP，`requires_internet=false` 的工具默认开启；外网类（`requires_internet=true`）默认关闭，需管理员后台「系统设置 → 外网工具开关」开启。所有工具在 `MOCK_LLM=true` 下返回仿真数据，调用链路与真实环境完全一致。

### 5.1 工具总清单（共 35 个，分 8 大类）

> 所有工具统一遵循 Function Calling 规范（入参 / 出参 JSON-Schema），由 Agent 的 Planner 根据自然语言自动选择调用，或由管理员在后台统一启停 / 配置可见角色。`requires_internet=true` 的外网工具默认关闭，需管理员后台「系统设置 → 外网工具开关」开启。所有工具在 `MOCK_LLM=true` / `MOCK_TOOLS=true` 下返回仿真数据，调用链路与真实环境完全一致。

**① 基础通用（`general`，全员可用）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `get_current_time` | 当前时间 / 时区 | `timezone`（可选，IANA 时区名） | 全员 | 否 | 获取日期 / 星期 / 时间 / 时间戳 |
| `math_calculate` | 数学表达式计算 | `math_expression`（如 `(1+2)*3/sqrt(9)`） | 全员 | 否 | 精确求解算式，避免 LLM 直接算数产生幻觉 |

**② 企业协同办公（`office`，全员）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `feishu_send` | 飞书消息发送 | `target`(选填)、`content`(必填) | 全员 | 否 | 发送到群或个人 |
| `email_query` | 企业邮件检索 | `keyword`、`limit`(选填) | 全员 | 是 | 业务往来邮件列表 |
| `email_send` | 企业邮件发送 | `to`、`subject`、`body` | 全员 | 是 | 发送成功回执 |
| `doc_search` | 在线文档检索 | `keyword` | 全员 | 否 | 语雀 / Confluence 文档片段 |
| `meeting_minutes` | 会议纪要提取 | `text` | 全员 | 否 | 结构化纪要（决议 / 待办 / 负责人） |

**③ 研发技术（`dev`，仅 `tech` / `admin`）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `github_search_repo` | GitHub 仓库检索 | `keyword`(搜仓库) / `repo`(owner/name 列分支) | tech / admin | 否 | 按关键词搜索仓库基础信息，或列出某仓库所有分支 |
| `swagger_parse` | 接口文档解析 | `path`、`method` | tech / admin | 否 | 接口说明 + 调用示例 |
| `git_weekly_report` | Git 周报生成 | `repo`(owner/name)、`author`(可选)、`branch`(可选)、`since`/`until`(可选) | tech / admin | 否 | 读取 GitHub 某仓库提交记录，按 conventional-commit 类型分类汇总，生成 Markdown 周报 |

**④ 业务系统（`business`，按部门 / 角色隔离）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `crm_query` | CRM 客户查询 | `keyword` | sales / admin | 是 | 客户 / 商机（**行权限：仅本人客户**） |
| `hr_query` | HR 人事查询 | 无 | hr / admin | 是 | 本人考勤 / 假期 / 简历（**仅本人**） |
| `finance_query` | 财务 ERP 查询 | `kind`: `invoice` \| `revenue` | finance / admin | 是 | 报销 / 发票 / 营收（**仅财务岗**） |
| `oa_start` | OA 审批发起 | `type`(出差 / 采购 / 请假) | 全员 | 否 | 审批单号 |
| `oa_status` | OA 审批进度 | `approval_id` | 全员 | 否 | 当前审批节点 |

**⑤ 计算 & 可视化（`compute`，全员）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `python_sandbox` | 安全 Python 沙箱 | `code` | 全员 | 否 | 计算结果（**屏蔽 `import os` / `subprocess` / 文件删除等高危指令**） |
| `chart_generate` | 图表生成 | `type`(line/bar/mermaid)、`title`、`labels`、`values`、`code`(选填) | 全员 | 否 | 折线 / 柱状 / Mermaid 图数据 |
| `currency_convert` | 汇率换算 | `amount`、`from`、`to` | 全员 | 否 | 换算金额 |
| `worktime_cost` | 工时成本换算 | `hours`、`hourly_rate` | 全员 | 否 | 成本合计 |

**⑥ 自研内部业务（`custom`，全员）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `inventory_query` | 库存查询 | `keyword` | 全员 | 否 | 自研接口库存数据 |
| `product_param` | 产品参数查询 | `model` | 全员 | 否 | 自研接口产品参数 |
| `quote_generate` | 客户报价单生成 | `items` | 全员 | 否 | 生成客户报价单 |

**⑦ 外网检索（`external`，默认关闭，管理员按需开启）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `weather_query` | 天气查询 | `city` | 全员 | 否 | 天气预报 |
| `calendar_query` | 日历查询 | `date` | 全员 | 否 | 当日日程 |
| `whois_query` | 域名 / IP 查询 | `domain` | 全员 | 否 | 注册信息 |
| `web_search` | 公开资料检索 | `query` | 全员 | 否 | 公开检索摘要 |

**⑧ 企业知识库 & 数据库（`rag`，按部门隔离）**

| 技术标识 | 显示名 | 入参要点 | 可见角色 | 脱敏 | 说明 |
|---|---|---|---|---|---|
| `vector_search` | 知识库向量检索 | `query`、`top_k`(可选)、`metadata_filter`(可选) | 全员 | 否 | 混合检索（向量 + 关键词 → 重排）文档片段，返回带来源 / 页码 / 章节的引用 |

> **RAG 用法**：`vector_search` 通过语义检索定位相关文档片段（带来源与页码），按文档 `department` 做部门隔离（非本人部门且非 `general` 的文档不可见）。

### 5.2 怎么调用（两种入口）

工具调用**统一走 Agent 对话入口**，没有独立的「单工具 POST 接口」——由 Planner 决定调哪个、怎么串行/并行编排。

**入口 1：前端对话窗口（员工日常使用）**
在聊天框输入自然语言即可，例如：
```
统计本月销售数据 → 生成趋势图 → 发销售群 → 写入周报文档
```
Agent 会自动拆成 3 步：`crm_query` → `chart_generate` → `feishu_send`，并在界面以**步骤时间线**实时展示每步状态与结果。

**入口 2：HTTP API（供前端 / 研发插件 / 第三方集成）**

- 非流式： `POST /api/v1/chat`
  ```json
  请求：{ "message": "查一下我的客户张三", "conversation_id": "可选，不传则新建会话" }
  响应：{
    "conversation_id": "...",
    "answer": "✅ CRM 客户查询：...",
    "steps": [ { "tool": "crm_query", "status": "success", "result": {...} } ],
    "used_rag": false,
    "rag_sources": []
  }
  ```
- 流式（推荐前端用，实时步骤）： `POST /api/v1/chat/stream`，返回 SSE 事件流：
  - `rag`：是否命中权限内知识库（`sources` 列出文档标题）
  - `plan`：Planner 拆解出的步骤列表（`mode=none` 表示直接回答、未调用工具；`mode=single` 单工具；`mode=multi` 多步）
  - `step_start`：`{tool, display}` 某工具开始执行
  - `step_result`：该步骤完整返回（见 5.3 结构）
  - `answer`：最终汇总文本
  - `done`：`{conversation_id}`

**强制指定工具**：直接用具名动词即可提高命中率，例如「帮我 review MR 128」「检索 order 相关代码」「生成一张 Mermaid 流程图」。

### 5.3 怎么判断是否调用成功

每次工具执行都会产生一个**步骤结果对象（step entry）**，关键字段：

```json
{
  "tool": "crm_query",            // 技术标识
  "display_name": "CRM 客户查询",
  "display": "CRM 客户查询",
  "args": { "keyword": "张三" },  // 实际入参
  "status": "success",            // ★ 成功判定字段：success / failed
  "result": {
    "ok": true,                   // ★ 工具自身是否成功
    "kind": "table",              // 结果类型：text | table | file | chart
    "text": "",                   // kind=text 时的文本
    "table": { "columns": [...], "rows": [[...]] },  // kind=table
    "file":  { "name": "...", "object_key": "...", "url": "..." },  // kind=file
    "chart": { "type": "line", "data": {...} },      // kind=chart
    "error": null                 // kind 任意；失败时的错误原因
  },
  "error": null                   // 失败时的错误原因（status=failed 时有值）
}
```

**成功的三重判定（全部满足即成功）：**
1. `status == "success"`（执行器级别的最终状态）；
2. `result.ok == true`（工具适配器返回成功）；
3. `result.error` 为 `null` 且 `result.kind` 有对应内容（文本/表格/文件/图表）。

最终 `answer` 文本会以 `✅ {显示名}：…` 汇总成功步骤，例如 `✅ CRM 客户查询：返回 3 条记录。`；返回文件时给出文件名，返回图表时给出「已生成图表」。

**失败判定（`status == "failed"` 或 `result.ok == false`）：** 此时 `error` 字段说明原因，`answer` 中以 `❌ {显示名} 失败：{原因}` 标注。

**常见失败原因（都来自 `error` 字段）：**

| 现象 | error 文案 | 含义 / 处理 |
|---|---|---|
| 工具被停用 | `工具「xxx」已停用` | 管理员后台「工具管理」重新启用 |
| 无权限 | `当前角色(xxx)无权使用工具「yyy」` | 用户角色不在 `allowed_roles` 内（如销售调 `github_*` / `git_*`） |
| 外网未开启 | `外网检索工具当前未开启（需管理员在后台启用）` | 后台「系统设置」打开外网开关 |
| 工具未注册 | `工具「xxx」缺少适配器实现` | 适配器未实现 / 未在 `ADAPTERS` 注册 |
| 执行异常 | `工具执行异常：TypeError: …` | 适配器运行时报错，查后端日志 |
| 工具不存在 | `工具「xxx」不存在或未授权` | Planner 引用的工具名未在库里 |

**审计侧佐证**：每次工具调用都会在 `audit_logs` 写入一条 `action=tool_call` 记录（含 `resource=工具名`、`detail.args`、`detail.status`、操作 IP）。对 `crm_query / hr_query / finance_query / email_query` 这类敏感工具，**调用成功时 `sensitive=true`，会在管理员后台「敏感操作告警面板」高亮**。因此「是否成功 + 是否触敏」在审计日志里也能一眼核对。

> 小结：前端看步骤时间线的 ✅/❌ 与最终 `answer`；API 看每个 `step.status` 与 `result.ok`；合规审计看 `audit_logs`。三者一致即代表工具调用真实成功。

---

## 六、接入真实系统（关掉 Mock，接真环境）

项目开箱即 `MOCK_LLM=true` + `MOCK_TOOLS=true` 跑仿真数据。要接真实环境，核心是 **两个开关 + 一份连接配置**：

### 6.1 三步切换真实模式

1. 编辑 `backend/.env`（或 `.env.example`）：
   ```ini
   MOCK_LLM=false      # 走真实大模型（已配 deepseek-chat / deepseek-reasoner）
   MOCK_TOOLS=false    # 工具走真实调用；未配置的系统会明确报错，不再返回假数据
   ```
2. 在 `.env` 底部「真实系统集成配置」填入各系统的地址与令牌（见 6.2 映射表）。**填了即真实调用，留空则调用时返回清晰错误**（如 `未配置 CRM_BASE_URL…`）。
3. 重启后端：`uvicorn app.main:app --reload` 或 `docker compose up --build`。

> 小提示：`MOCK_TOOLS=false` 但某系统地址留空时，该工具不会静默给假数据，而是直接失败并提示缺哪个配置 —— 方便你逐项点亮真实系统。

### 6.2 各工具 → 环境变量映射

| 工具 | 需配置的环境变量 | 调用方式（默认实现） |
|---|---|---|
| `feishu_send` 飞书消息 | `FEISHU_WEBHOOK_URL` | POST 飞书自定义机器人 webhook |
| `email_send` 发邮件 | `MAIL_SMTP_HOST`/`MAIL_SMTP_PORT`/`MAIL_USER`/`MAIL_PASSWORD` | SMTP_SSL 真实发送 |
| `email_query` 收邮件 | `MAIL_IMAP_HOST` 等 | 需在 `adapters/office.py` 实现 IMAP（当前演示） |
| `doc_search/create/update` 文档库 | `DOC_BASE_URL`/`DOC_TOKEN` | 调语雀/Confluence 等 REST |
| `github_search_repo` | `GITHUB_BASE_URL`/`GITHUB_TOKEN` | GitHub `/search/repositories` 与 `/repos/{owner}/{repo}/branches` |
| `swagger_parse` | `SWAGGER_BASE_URL` | 拉取 OpenAPI JSON 解析 |
| `crm_query` | `CRM_BASE_URL`/`CRM_TOKEN` | `GET {base}/customers?keyword=&owner=`（owner 自动带入，实现行权限） |
| `hr_query` | `HR_BASE_URL`/`HR_TOKEN` | `GET {base}/employees/me` |
| `finance_query` | `FINANCE_BASE_URL`/`FINANCE_TOKEN` | `GET {base}/invoice` 或 `/revenue` |
| `oa_start` | `OA_BASE_URL`/`OA_TOKEN` | `POST {base}/apply` |
| `oa_status` | 同上 | `GET {base}/approvals/{id}` |
| `inventory_query` | `INVENTORY_BASE_URL`/`INVENTORY_TOKEN` | `GET {base}/search?keyword=` |
| `product_param` | `PRODUCT_BASE_URL`/`PRODUCT_TOKEN` | `GET {base}/{model}` |
| `quote_generate` | `QUOTE_BASE_URL`/`QUOTE_TOKEN` | `POST {base}/generate` |
| `weather_query` | 无需（Open-Meteo 免密钥） | 真实天气 API |
| `whois_query` | 无需（RDAP 免密钥） | 真实 RDAP 查询 |
| `calendar_query` | `BIZ_BASE_URL`/`BIZ_TOKEN`（business-systems/biz 服务 `/calendar/events`） | 自研日历接口，与四个业务工具共用 biz 服务 |
| `web_search` | Tavily Search（可选，填入 `TAVILY_API_KEY`）/ 维基百科官方 API（免密钥兜底） | 真实公开检索 |
| `currency_convert` | `EXCHANGE_RATE_API_KEY`（可选） | 实时汇率；未配置用静态汇率 |
| `git_weekly_report` Git 周报 | `GITHUB_BASE_URL`/`GITHUB_TOKEN` | 调用 GitHub `/repos/{owner}/{repo}/commits`，无需本地 git CLI |
| `vector_search` 知识库 | `EMBEDDING_BASE_URL`/`EMBEDDING_MODEL`、`KNOWLEDGE_DB_*` | 知识库检索（详见 6.3） |

> 业务/自定义类工具是公司自研接口，路径、字段各不相同。**默认实现**以「`GET(<base>?keyword=...)` / `POST(<base>)` + Bearer 令牌」发起，并把返回 JSON 自动脱敏（手机/邮箱/身份证/薪资/税号/账号）。若贵司接口约定不同，**直接改 `adapters/business.py` / `adapters/custom.py` 中对应函数体即可，调度框架、权限、审计、脱敏全部复用，无需动其他代码。**

### 6.3 大模型 & RAG

- **真实大模型**：`LLM_BASE_URL` 指向内网 vLLM（暴露 OpenAI 接口），模型名已设为 `deepseek-chat` / `deepseek-reasoner`；用 DeepSeek 官方云则改为 `https://api.deepseek.com/v1` 并填 `LLM_API_KEY`。`MOCK_LLM=false` 后 Planner 改为基于 Function Calling 的真实推理。
- **真实 RAG（向量召回）**：`EMBEDDING_BASE_URL` 指向本项目内置的本地 Embedding 服务 `backend/embedding_service`（已加载 `bge-small-zh-v1.5`，512 维，OpenAI 兼容 `/v1/embeddings`，默认 `http://localhost:8088/v1`）。`MOCK_LLM=false` 时检索自动切换为 `pg_vector` 余弦相似度；若 `EMBEDDING_BASE_URL` 为空或服务不可用，则自动回退关键词检索，对话不会因 embedding 故障而中断。可替换为任意兼容的 embedding 服务（vLLM / TEI），注意模型名与 `EMBEDDING_DIM=512` 必须匹配。
- **真实 RAG（精排）**：`RERANK_BASE_URL` 指向本项目内置的本地 Rerank 服务 `backend/rerank_service`（已加载 `bge-reranker-v2-m3`，OpenAI 兼容 `/rerank`，默认 `http://localhost:8089`）。向量/关键词召回的候选片段会经重排后取 Top-K；若 `RERANK_BASE_URL` 为空或服务不可用，则跳过精排、保留原召回序。
- **对象存储**：默认写 MinIO；未部署时自动回退本地 `backend/data/files/` 并经 `/api/v1/files/local/` 下载。

### 6.4 新增 / 修改工具（无需改框架）

1. 编辑 `backend/app/tools/adapters/<类别>.py`，实现 `async def xxx(args, ctx) -> ToolResult`，在模块 `ADAPTERS` 字典注册。
2. 管理员后台「工具管理」或编辑 `app/seed.py` 的 `TOOLS` 元组增加一条 `Tool` 记录（`adapter` 填注册 key，`allowed_roles` 控角色，`mask_sensitive` 控脱敏，`requires_internet` 控外网）；重启服务后由启动事件幂等写入。
3. 重启后端即可生效。

---

## 七、实战使用场景（端到端示例）

下面用「自然语言输入 → Agent 拆解的工具调用链 → 产出」展示工具如何被串联使用。所有示例均可在前端对话框直接输入。

### 7.1 知识库精确问答（RAG 工具对）

**输入**：`知识库里关于退款流程是怎么规定的？引用具体条款。`

**调用链**：
1. `vector_search` → `{"query":"退款流程 条款"}`：混合检索命中相关文档片段，返回带来源文档、页码、章节的引用。
2. 基于原文片段生成带引用（文档名 + 页码）的答案。

### 7.2 生成本周工作周报（Git 周报）

**输入**：`生成本周 Git 提交周报，仓库在 /data/repos/backend`

**调用链**：
1. `git_weekly_report` → `{"repo":"octocat/Hello-World","since":"2026-07-20","until":"2026-07-26"}`：调用 GitHub `/repos/{owner}/{repo}/commits`，按 `feat/fix/docs/refactor…` 分类汇总，输出 Markdown 周报（含按类型统计表）。

**前置**：配置 `GITHUB_BASE_URL`（默认 `https://api.github.com`）与 `GITHUB_TOKEN`（具备 repo 读权限的 PAT）。

### 7.3 跨系统多步骤任务

**输入**：`把本月华东区销售数据做成趋势图，发到销售群，并写入周报文档`

**调用链**：
1. `crm_query` → 按区域筛选商机/业绩（行权限：仅本人客户，越权自动过滤）。
2. `chart_generate` → `{"type":"line","labels":[...],"values":[...]}` 生成折线图数据。
3. `feishu_send` → 把图表与摘要推送到销售群。

### 7.4 全工具「一句话怎么问」速查表（35 个工具全覆盖）

下面按 8 大类列出**每个工具的技术标识 + 直接可复制到对话框的自然语言示例**。Planner 会据语义自动选工具；用方括号里的「具名动词」能进一步提高命中率。

#### ① 基础通用（全员）

| 工具 | 怎么问（直接输入） |
|---|---|
| `get_current_time` 当前时间/时区 | `现在几点？` / `纽约现在几点？`（可加 `timezone` 如 `America/New_York`） |
| `math_calculate` 数学表达式计算 | `算一下 (1+2)*3/sqrt(9) 等于多少` |

#### ② 企业协同办公（全员）

| 工具 | 怎么问（直接输入） |
|---|---|
| `feishu_send` 飞书消息发送 | `发飞书消息到销售群：本周周会改到周五下午三点` |
| `email_query` 企业邮件检索 | `查一下和华为客户的往来邮件` / `最近一周关于合同的邮件有哪些` |
| `email_send` 企业邮件发送 | `给 zhangsan@company.com 发邮件，主题「Q3 报价」，内容见附件说明` |
| `doc_search` 知识库检索（RAG 优先，回退语雀/Confluence） | `搜一下"退款流程"相关的文档` / `检索知识库里关于报销的规定` |
| `meeting_minutes` 会议纪要提取 | `帮我从下面的会议记录里提取决议、待办和负责人：（粘贴会议文本）` |

#### ③ 研发技术（仅 `tech` / `admin` 角色）

| 工具 | 怎么问（直接输入） |
|---|---|
| `github_search_repo` GitHub 仓库检索 | `搜一下 fastapi 相关的仓库` / `列出 owner/repo 的所有分支` |
| `swagger_parse` 接口文档解析 | `解析 /api/v1/orders 的 GET 接口` |
| `git_weekly_report` Git 周报生成 | `生成本周 Git 提交周报，仓库是 octocat/Hello-World` |

#### ④ 业务系统（按部门 / 角色隔离，注意行权限）

| 工具 | 怎么问（直接输入） |
|---|---|
| `crm_query` CRM 客户查询 | `查一下我的客户张三` / `搜一下关键词"华东"的商机`（销售/管理员，仅本人客户） |
| `hr_query` HR 人事查询 | `查一下我的考勤和剩余年假`（人事/管理员，仅本人） |
| `finance_query` 财务 ERP 查询 | `查询本月发票` / `查一下本季度营收`（财务/管理员） |
| `oa_start` OA 审批发起 | `帮我发起一个出差审批，去上海三天` / `发起采购申请，预算 2 万` |
| `oa_status` OA 审批进度 | `查一下审批单 OA2026070001 到哪一步了` |

#### ⑤ 计算 & 可视化（全员）

| 工具 | 怎么问（直接输入） |
|---|---|
| `chart_generate` 图表生成 | `生成一张 Mermaid 流程图，描述用户登录流程` / `把 [12,19,8,23] 画成柱状图` |
| `currency_convert` 汇率换算 | `100 美元能换多少人民币` |
| `worktime_cost` 工时成本换算 | `工时成本：20 小时 × 200 元/小时 是多少` |

#### ⑥ 自研内部业务（全员）

| 工具 | 怎么问（直接输入） |
|---|---|
| `inventory_query` 库存查询 | `查一下 交换机 S100 的库存还剩多少` |
| `product_param` 产品参数查询 | `查一下型号 交换机 S100 的产品参数` |
| `quote_generate` 客户报价单生成 | `给客户生成报价单，含 交换机 S100 10 台、主机 X1产品 5 台` |
| `calendar_query` 日历查询 | `今天我有什么日程安排` |

#### ⑦ 外网检索（默认关闭，需管理员后台开启）

| 工具 | 怎么问（直接输入） |
|---|---|
| `weather_query` 天气查询 | `北京今天天气怎么样`  |
| `whois_query` 域名/IP 查询 | `查一下 example.com 的域名注册信息` / `查 IP 8.8.8.8 归属` |
| `web_search` 公开资料检索 | `狄仁杰 公开资料` / `查一下特斯拉最新新闻`（自动剥离"公开资料"等噪声词，实体过滤单字/姓氏无关页） |

#### ⑧ 企业知识库 & 数据库（按 `department` 隔离）

| 工具 | 怎么问（直接输入） |
|---|---|
| `vector_search` 知识库向量检索 | `知识库里关于退款流程是怎么规定的？` |

> **使用提示**
> - 外网类（⑦）默认关闭：先在管理员后台「系统设置 → 外网工具开关」打开，才能问天气/日历/域名/公开资料。
> - 研发类（③）需 `tech` / `admin` 角色；业务类（④）按角色与行权限隔离（如销售只能看自己的客户）。
> - 知识库（⑧）非 `general` 且非本部门的文档不可见。
> - **检索路由**：含「知识库 / 文档」的提问会走 `doc_search`，它**优先检索内部 RAG 知识库**，未命中再自动回退到语雀 / Confluence 在线文档库；若明确写「语雀 / confluence / 在线文档 / 文档库」则直接查外部文档库、跳过 RAG。纯向量检索可用「语义检索 / 向量检索」触发 `vector_search`。
> - 想强制命中某工具，直接用它的具名动词即可，例如「帮我 review MR 128」「搜一下退款流程文档」「发起一个出差审批」。

---

## 八、常见问题与故障排查（FAQ）

**Q1：启动报 `ModuleNotFoundError: No module named 'app.seed'`**
A：`seed.py` 必须位于 `backend/app/seed.py`（在 `app` 包内），与 `from app.seed import ...` 一致。若误放在 `backend/` 根目录，请移入 `backend/app/`。启动请用：
```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
不要直接用 `python -m app.main`（需额外把 `backend` 加入 `PYTHONPATH`）。

**Q2：pip 安装报依赖冲突（mcp / fastmcp-slim 要求 pydantic≥2.11、uvicorn≥0.31、python-dotenv≥1.1）**
A：升级这些基础包到兼容版本（已在 `requirements.txt` 锁定：`pydantic==2.11.7`、`uvicorn[standard]==0.34.0`、`python-dotenv==1.1.0`、`pydantic-settings==2.9.1`）。国内环境加清华镜像并放大超时：
```powershell
pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 5
```

**Q3：安装 `psycopg2` 时 `TimeoutError: The read operation timed out`**
A：同上设置镜像与 `--timeout 120 --retries 5`；或改用预编译的 `psycopg2-binary`（已在依赖中）。

**Q4：MinIO 没部署，文件上传会失败吗？**
A：不会。`storage.py` 会自动回退到本地磁盘 `backend/data/files/`，并经 `/api/v1/files/local/` 提供下载，日志会打印回退信息。

**Q5：调用外网工具（天气 / 搜索等）无返回或报错**
A：外网类工具 `requires_internet=true`，默认关闭。需管理员在后台「系统设置 → 外网工具开关」开启；或在 `.env` 中相应配置。

**Q6：工具返回「无权限」或查不到数据**
A：检查两点——① 工具 `allowed_roles` 是否包含当前用户角色；② 知识库文档 `department` 是否与当前用户部门匹配（非 `general` 且非本部门不可见）。行权限工具（如 `crm_query`）还会按用户过滤数据。

**Q7：新增 / 修改工具后在后台看不到？**
A：`app/seed.py` 的 `TOOLS` 是由服务启动的 `lifespan` 事件**幂等写入**的——新增记录会写入，已存在的同名工具不会重复。改完 `adapters/` 实现与 `seed.py` 后，**重启后端服务**即可生效；并确认已在 `registry.py` 的 `ADAPTERS` 中注册。

**Q8：Git 仓库读取提示越权或不存在**
A：`git_weekly_report` 通过 GitHub REST API（`GITHUB_BASE_URL`/`GITHUB_TOKEN`）拉取提交，无需本地 git CLI。请确认 `repo_path` 指向正确的 `owner/repo`，且 `GITHUB_TOKEN` 对该仓库有读权限；私有仓库需 Token 具备 `repo` 范围。

---

## 九、目录结构

```
backend/
  app/
    config.py              配置
    main.py                FastAPI 入口（建表 / 扩展 / seed / 路由）
    db/                    SQLAlchemy 模型 + 会话（Postgres + pg_vector）
    core/                  security(RBAC/JWT) / masking(脱敏) / audit(审计) / storage(MinIO) / runtime_cfg
    schemas/               Pydantic 请求响应模型
    tools/
      base.py              工具基类型 + Function Calling schema
      registry.py          工具注册中心 + 调度（权限 / 外网 / 脱敏）
      adapters/            九类工具适配器（general/office/dev/gitweekly/business/compute/custom/external/knowledge）
    agent/                 LLM / memory / rag / planner / executor / graph(LangGraph)
    services/file_processing.py   文档解析 + 切片 + 向量化入库
    api/routers/           auth / chat(流式SSE) / tools / admin / knowledge / files
    app/seed.py            初始用户 / 工具 / 提示词（幂等，由 main.py 启动事件调用）
  requirements.txt  Dockerfile  .env.example
frontend/                  Vue3 + Element Plus 聊天与管理前端



docker-compose.yml         一键编排（pgvector / redis / minio / backend / frontend / eureka / gateway / crm / hr / finance / oa）
```

> 技术栈：Python 3.11 · FastAPI · LangGraph · SQLAlchemy 2.0 · PostgreSQL + pg_vector · Redis · MinIO · Vue3 · Element Plus · Vite；

---

## 十、仿真业务系统（CRM / HR / 财务 ERP / OA）

平台配套一套独立仓库的 **仿真业务系统**（见 `business-systems/`），用于在没有真实后端时驱动 CRM / HR / 财务 ERP / OA 四类工具的完整调用链路与权限隔离演示（行权限、部门隔离、脱敏等）。它由 `docker-compose.yml` 一键编排（crm / hr / finance / oa），业务接口地址通过 `.env` 中的 `CRM_SERVICE_URL` / `HR_SERVICE_URL` / `FINANCE_SERVICE_URL` / `OA_SERVICE_URL` 配置。关闭 Mock 后，工具适配器将请求转发到这些服务；服务未启动时工具返回 `mock` 仿真数据，链路与真实环境一致。

> 各微服务的端口、接口契约与数据库初始化脚本见 `business-systems/` 下对应子目录的 README。