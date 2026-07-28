"""Tool adapters (层级 4 工具适配微服务层).

Each module exposes `ADAPTERS: dict[str, Callable]` mapping an adapter key to an
`async (args, ctx) -> ToolResult` implementation. They currently return mocked
but realistic data; wiring real 飞书/GitHub/CRM endpoints only requires editing
the adapter body. Row-level isolation and data masking are applied here.
"""
