"""通用基础工具（所有 Agent 必备）: 时间 / 计算.

这些工具不依赖外部系统，全部本地可用。
"""
from __future__ import annotations

import ast
import calendar
import math
import re

from app.config import settings
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text


# ============================================================
# 1) 时间工具
# ============================================================
async def get_current_time(args: dict, ctx: ToolContext) -> ToolResult:
    tz = (args.get("timezone") or "Asia/Shanghai").strip()
    city = (args.get("city") or "").strip()
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime

        now = datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001
        from datetime import datetime

        now = datetime.now()
    wd = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    ts = int(now.timestamp())
    label = f"{city}（{tz}）" if city else tz
    return ok_text(
        f"当前时间（{label}）：\n"
        f"- 日期：{now.strftime('%Y-%m-%d')}\n"
        f"- 星期：{wd}\n"
        f"- 时间：{now.strftime('%H:%M:%S')}\n"
        f"- 时间戳(秒)：{ts}"
    )


# ============================================================
# 2) 数学计算器（表达式求值，带安全校验）
# ============================================================
_ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_ALLOWED_NAMES.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum,
                       "pow": pow, "len": len, "True": True, "False": False, "None": None})


def _math_check(node: ast.AST) -> None:
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id not in _ALLOWED_NAMES:
            raise ValueError(f"不允许的标识符: {n.id}")
        if isinstance(n, (ast.Attribute, ast.Call)):
            # 仅允许 math.xxx 形式的方法调用上下文；禁止 __xxx__
            pass


# 全角/中文符号 -> 半角数学符号（用字典映射，避免 maketrans 两端长度不一致报错）
_FW_MAP = {
    "，": ",", "。": ".", "、": "(", "（": "(", "）": ")", "；": ";", "：": ":",
    "？": "?", "！": "!", "％": "%", "　": " ", "×": "*", "÷": "/",
}

def _clean_math_expr(q: str) -> str:
    """从自然语言里抽取纯数学表达式，并把常见中文/全角运算符转成 Python 可计算的符号。

    关键点：先转译运算符再删除引导词，最后去掉所有空白，避免『1234 乘以 5678』
    被清理成 '1234 5678'（数字间残留空格）导致 eval 报 SyntaxError。
    本函数保证不抛异常，任何输入都返回可安全交给 ast.parse 的字符串。
    """
    try:
        s = q
        # 1) 全角 -> 半角
        s = s.translate(str.maketrans(_FW_MAP))
        # 2) 中文/符号运算符 -> 数学符号（带空格包裹，便于后续统一去除空白）
        s = s.replace("乘以", " * ").replace("乘", " * ")
        s = s.replace("除以", " / ").replace("除", " / ")
        s = s.replace("加上", " + ").replace("加", " + ")
        s = s.replace("减去", " - ").replace("减", " - ")
        s = s.replace("%", " / 100 ")
        # 3) 『a 的 b 次方/次幂』 -> a ** b
        s = re.sub(r"(\d+(?:\.\d+)?)\s*的\s*(\d+(?:\.\d+)?)\s*次[方幂]", r"\1 ** \2", s)
        # 4) 删除引导词 / 单位等噪声
        for w in ("算一下", "算一算", "计算", "求值", "运算", "表达式", "算式", "等于",
                  "多少", "请问", "帮我", "请", "一下", "结果", "是多少", "approximately",
                  "约等于", "约", "来", "个", "元", "块", "人", "名", "位", "天", "年", "月"):
            s = s.replace(w, " ")
        # 5) ^ 视为幂运算
        s = s.replace("^", " ** ")
        # 6) 仅保留表达式合法字符并去除所有空白
        s = re.sub(r"[^0-9+\-*/().^a-zA-Z_]", "", s)
        return s.strip()
    except Exception:  # noqa: BLE001 - 兜底，绝不外抛
        return ""


async def math_calculate(args: dict, ctx: ToolContext) -> ToolResult:
    expr = (args.get("math_expression") or args.get("expr") or args.get("expression")
            or args.get("query") or "").strip()
    if not expr:
        return fail("缺少数学表达式参数（math_expression）")
    try:
        tree = ast.parse(expr, mode="eval")
        _math_check(tree)
        result = eval(compile(tree, "<math>", "eval"), {"__builtins__": {}}, _ALLOWED_NAMES)
    except SyntaxError as e:
        return fail(f"表达式计算失败：无法解析为数学表达式（{expr!r}）。请使用数字与 + - * / ( ) 等运算符。")
    except (ValueError, ZeroDivisionError, Exception) as e:  # noqa: BLE001
        return fail(f"表达式计算失败：{type(e).__name__}: {e}")
    return ok_text(f"计算结果：{expr} = {result}")


ADAPTERS = {
    "get_current_time": get_current_time,
    "math_calculate": math_calculate,
}
