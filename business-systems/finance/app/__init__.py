"""财务 ERP 仿真业务系统（独立服务，端口 8003）。

与 AI Agent 平台解耦，作为真实外部业务系统被 Agent 工具（finance_query）调用。
鉴权方式同 CRM/HR：共享服务令牌 + 网关透传身份头（X-Act-User / X-Act-Role），
仅财务(finance)与管理员(admin)可访问，敏感字段（税号 / 收款账号）仅对财务/管理员可见。
"""