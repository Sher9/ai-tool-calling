"""HR 仿真业务系统（独立服务，端口 8002）。

与 AI Agent 平台解耦，作为真实外部业务系统被 Agent 工具（hr_query）调用。
鉴权方式同 CRM：共享服务令牌 + 网关透传身份头（X-Act-User / X-Act-Role），
敏感字段（身份证 / 薪资）仅对人事(HR)与管理员(admin)可见。
"""