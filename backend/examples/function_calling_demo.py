#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Function Calling 教学 Demo（单文件、零依赖、可直接运行）。

演示一条完整的 ReAct 式 function calling 链路：
  1) 把工具定义成 OpenAI function schema（给 LLM 的“说明书”）
  2) 调 LLM（/chat/completions），带 tools + tool_choice="auto"
  3) 解析模型返回的 tool_calls，本地执行对应的 Python 函数
  4) 把执行结果以 role="tool" 消息回灌给模型（这是 function calling 的核心）
  5) 循环，直到模型不再返回 tool_calls、给出最终自然语言答案

运行方式：
  # 默认 MOCK 模式，无需联网/模型，直接看流程
  python function_calling_demo.py
  python function_calling_demo.py "查北京天气"

  # 真实模式：指向你自己的 OpenAI 兼容 vLLM（如 DeepSeek / Qwen / GLM）
  MOCK=0 LLM_BASE_URL=http://localhost:8000/v1 LLM_API_KEY=EMPTY LLM_MODEL=deepseek-chat \
      python function_calling_demo.py "帮我算 1 到 10 的平方和"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# 让 demo 在 Windows 默认 gbk 控制台也能正常打印中文/特殊字符
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


# ===========================================================================
# 1) 工具实现（本地 Python 函数）
# ===========================================================================
def get_weather(city: str) -> str:
    """模拟天气查询工具（真实项目里换成调用天气 API）。"""
    return f"{city} 今天晴，26°C，微风，适合出行。"


# 工具名 -> 本地实现，dispatch 时按名字找
TOOL_IMPLS = {
    "get_weather": get_weather,
}


# 工具 schema：这就是发给 LLM 的 function calling 描述
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某城市今日天气。",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
]


# ===========================================================================
# 2) 调 LLM（OpenAI 兼容 /chat/completions）
# ===========================================================================
def call_llm(messages: list[dict], tools=None) -> dict:
    """返回 {"tool_calls": [...]} 或 {"content": "..."}。"""
    if os.environ.get("MOCK", "1") != "0":
        return _mock_llm(messages)
    # ---- 真实模式 ----
    payload = {
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "messages": messages,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    msg = data["choices"][0]["message"]
    if msg.get("tool_calls"):
        calls = [
            {
                "id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"] or "{}"),
            }
            for tc in msg["tool_calls"]
        ]
        return {"tool_calls": calls}
    return {"content": msg.get("content", "")}


def _mock_llm(messages: list[dict]) -> dict:
    """模拟模型：根据最后一条用户消息决定调哪个工具，或给最终答案。"""
    # 如果上下文里已经有 tool 结果，说明工具已执行过 -> 给最终答案
    if any(m["role"] == "tool" for m in messages):
        return {"content": "（模拟）我已根据工具返回的结果完成回答，详见上方步骤。"}
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if "天气" in last_user:
        return {"tool_calls": [
            {"id": "call_1", "name": "get_weather", "arguments": {"city": "北京"}}
        ]}
    return {"content": "你好，我是 demo。试着让我『查北京天气』。"}


# ===========================================================================
# 3) 执行工具（dispatch）
# ===========================================================================
def run_tool(name: str, args: dict) -> str:
    fn = TOOL_IMPLS.get(name)
    if not fn:
        return f"错误：未知工具 {name}"
    try:
        return fn(**args)
    except Exception as e:  # noqa: BLE001
        return f"工具执行失败：{e}"


# ===========================================================================
# 4) ReAct 主循环：LLM 决策 -> 执行 -> 回灌 -> 再决策
# ===========================================================================
def agent_loop(user_query: str, max_rounds: int = 5) -> str:
    messages = [{"role": "user", "content": user_query}]
    for _ in range(max_rounds):
        resp = call_llm(messages, TOOL_SCHEMAS)

        if "tool_calls" in resp:
            # 关键：把模型的 tool_calls 原样保留为一条 assistant 消息
            # （OpenAI 要求回灌时 assistant 必须带着 tool_calls 及各自 id）
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                        },
                    }
                    for c in resp["tool_calls"]
                ],
            })
            # 逐个执行工具，并以 role="tool" 把结果回灌
            for c in resp["tool_calls"]:
                result = run_tool(c["name"], c["arguments"])
                print(f"  [tool] 调用 {c['name']}({c['arguments']}) -> {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": c["id"],     # 必须对应 assistant 里的 id
                    "name": c["name"],
                    "content": result,
                })
            continue  # 带着工具结果再问一次模型

        # 模型不再返回 tool_calls => 最终答案
        return resp["content"]

    return "（达到最大轮次，模型仍未产出最终答案）"


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "查北京天气"
    print(f"用户：{q}")
    print("助手：")
    print(agent_loop(q))
