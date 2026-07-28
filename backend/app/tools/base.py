"""Base classes for tools and the execution context.

Every tool implements `async def run(args, ctx) -> ToolResult`. Tools are
registered centrally (层级 3.1 工具注册中心) and dispatched by their `adapter`
key. The function-calling schema consumed by the LLM is generated from the
Tool DB row (name / description / JSON-Schema parameters).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models import Tool


@dataclass
class ToolContext:
    """Identity & capability context passed to every tool invocation."""

    user_id: str
    username: str
    role: str
    department: str
    ip: str = ""
    raw: bool = False  # when True, skip data masking


@dataclass
class ToolResult:
    ok: bool = True
    kind: str = "text"  # text | table | file | chart
    text: str = ""
    # table => {"columns": [...], "rows": [[...]]}
    table: dict = field(default_factory=dict)
    # file => {"name", "object_key", "url"}
    file: dict = field(default_factory=dict)
    # chart => {"type": "line|bar|mermaid", "data": ...}
    chart: dict = field(default_factory=dict)
    error: str | None = None

    def to_payload(self) -> dict:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "text": self.text,
            "table": self.table,
            "file": self.file,
            "chart": self.chart,
            "error": self.error,
        }


def ok_text(text: str) -> ToolResult:
    return ToolResult(ok=True, kind="text", text=text)


def ok_table(columns: list[str], rows: list[list]) -> ToolResult:
    return ToolResult(ok=True, kind="table", table={"columns": columns, "rows": rows})


def ok_file(file: dict) -> ToolResult:
    return ToolResult(ok=True, kind="file", file=file)


def ok_chart(chart: dict) -> ToolResult:
    return ToolResult(ok=True, kind="chart", chart=chart)


def fail(error: str) -> ToolResult:
    return ToolResult(ok=False, kind="text", error=error)


def function_schema(tool: Tool) -> dict:
    """OpenAI-style function-calling schema derived from a Tool row."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters or {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
