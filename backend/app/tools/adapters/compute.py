"""计算 & 可视化工具: 图表生成 / 汇率工时换算."""
from __future__ import annotations

import ast
import io
import math

from app.config import settings
from app.core.http import aget
from app.core.storage import b64_png
from app.tools.base import ToolContext, ToolResult, ok_chart, ok_text


async def chart_generate(args: dict, ctx: ToolContext) -> ToolResult:
    ctype = args.get("type", "line")
    title = args.get("title", "图表")
    labels = args.get("labels", [])
    values = args.get("values", [])
    if ctype == "mermaid":
        code = (args.get("code") or "").strip()
        # 若用户传入的并非标准 mermaid 语法（多为自然语言描述），则包成一张基础流程图骨架，
        # 节点用描述中的关键词命名，保证前端能正常渲染。
        if not code or not (code.startswith("graph") or code.startswith("sequenceDiagram")
                            or code.startswith("flowchart") or "---" in code):
            kw = [w for w in re.split(r"[\s，。、；,.;]+", code or title) if w and len(w) > 1][:4]
            nodes = kw or ["开始", "处理", "结束"]
            lines = ["graph TD"]
            for i, n in enumerate(nodes):
                lines.append(f"  N{i}[{n}]")
            for i in range(len(nodes) - 1):
                lines.append(f"  N{i} --> N{i + 1}")
            code = "\n".join(lines)
        return ok_chart({"type": "mermaid", "data": code, "title": title})
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        if ctype == "bar":
            ax.bar(labels, values)
        elif ctype == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%")
        else:
            ax.plot(labels, values, marker="o")
        ax.set_title(title)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return ok_chart({"type": ctype, "data": b64_png(buf.read()), "title": title})
    except Exception as e:  # noqa: BLE001
        return ok_text(f"⚠️ 图表渲染失败（缺少 matplotlib？）：{e}")


async def currency_convert(args: dict, ctx: ToolContext) -> ToolResult:
    amount = float(args.get("amount", 0))
    frm = (args.get("from", "USD")).upper()
    to = (args.get("to", "CNY")).upper()
    rates = {"USD": 7.2, "CNY": 1.0, "EUR": 7.8, "JPY": 0.048}
    if settings.EXCHANGE_RATE_API_KEY:
        try:
            data = await aget(f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/latest/{frm}")
            conv = data.get("conversion_rates", {})
            if to in conv:
                out = amount * conv[to]
                return ok_text(f"💱 {amount} {frm} ≈ {out:.2f} {to}（实时汇率）")
        except Exception:  # noqa: BLE001
            pass  # 失败回退静态汇率
    if frm not in rates or to not in rates:
        return ok_text("不支持的币种（或未配置 EXCHANGE_RATE_API_KEY）。")
    cny = amount * rates[frm]
    out = cny / rates[to]
    return ok_text(f"💱 {amount} {frm} ≈ {out:.2f} {to}")


async def worktime_cost(args: dict, ctx: ToolContext) -> ToolResult:
    hours = float(args.get("hours", 0))
    rate = float(args.get("hourly_rate", 200))
    total = hours * rate
    return ok_text(f"⏱️ 工时 {hours} 小时 × 费率 {rate} 元/小时 = {total:.2f} 元")


ADAPTERS = {
    "chart_generate": chart_generate,
    "currency_convert": currency_convert,
    "worktime_cost": worktime_cost,
}
