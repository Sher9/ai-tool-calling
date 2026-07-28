"""CRM 仿真业务系统（独立服务，端口 8001）。

与 AI Agent 平台解耦，作为真实外部业务系统被 Agent 工具（crm_query）调用。
鉴权方式：Agent 携带共享服务令牌（SERVICE_TOKEN）并在请求头注入操作人身份
（X-Act-User / X-Act-Role），本服务据此做行级权限控制，模拟「网关透传身份」的内部微服务。
"""
