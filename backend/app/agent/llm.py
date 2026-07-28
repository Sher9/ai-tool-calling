"""LLM dispatch (层级 3.6 大模型调度服务).

When `MOCK_LLM=true` no external model is contacted; the planner falls back to a
deterministic rule engine so the platform runs out-of-the-box. Set `MOCK_LLM=false`
and point `LLM_BASE_URL` at an internal vLLM (OpenAI-compatible) endpoint to use a
real private model (Qwen / GLM / Llama3 ...).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


async def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> dict:
    """Call the OpenAI-compatible chat/completions endpoint.

    Returns either {"content": str} or {"tool_calls": [{"name", "arguments"}]}.
    """
    if settings.MOCK_LLM:
        raise RuntimeError("LLM is disabled (MOCK_LLM=true). Use the rule-based planner.")

    model = model or settings.LLM_LIGHT_MODEL
    temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # 12s 硬超时：防止内网推理服务无响应/过慢时请求无限期挂起
    async with httpx.AsyncClient(timeout=12) as client:
        resp = await client.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        )
        resp.raise_for_status()
        data = resp.json()
    msg = data["choices"][0]["message"]
    if msg.get("tool_calls"):
        calls = []
        for tc in msg["tool_calls"]:
            calls.append({"name": tc["function"]["name"], "arguments": _safe_json(tc["function"]["arguments"])})
        return {"tool_calls": calls}
    return {"content": msg.get("content", "")}


def _safe_json(s: str) -> dict:
    import json

    try:
        return json.loads(s or "{}")
    except json.JSONDecodeError:
        return {}
