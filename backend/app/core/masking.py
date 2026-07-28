"""Data masking / desensitization (数据脱敏).

Applied to tool outputs so that sensitive PII never reaches the user (or the
LLM context) unless the user has raw-access and the tool opted out of masking.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Built-in masking rules. Each rule: compiled regex -> replacement template.
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_EMAIL = re.compile(r"([A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+)")
_ID_CARD = re.compile(r"(?<!\d)(\d{6})(?:\d{8})(\d{4})(?!\d)")  # 18-digit mainland ID
_BANK_CARD = re.compile(r"(?<!\d)(\d{12})\d{4}(?!\d)")
_SALARY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(元|万元|RMB|CNY)")

# Keywords that flag a field as sensitive (used for dict/object masking)
_SENSITIVE_KEYS = ("phone", "mobile", "tel", "email", "mail", "id_card", "idcard",
                   "bank_card", "bankcard", "salary", "salary_amount", "income",
                   "身份证", "手机号", "电话", "邮箱", "银行卡", "工资", "薪资", "收入")


def _mask_phone(m: re.Match) -> str:
    return m.group(1)[:3] + "****" + m.group(1)[-4:]


def _mask_email(m: re.Match) -> str:
    local, domain = m.group(1).split("@", 1)
    if len(local) <= 2:
        masked = "*" * len(local)
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{domain}"


def _mask_id(m: re.Match) -> str:
    return m.group(1) + "********" + m.group(2)


def _mask_bank(m: re.Match) -> str:
    return m.group(1) + "****"


def mask_text(text: str) -> str:
    text = _ID_CARD.sub(_mask_id, text)
    text = _BANK_CARD.sub(_mask_bank, text)
    text = _PHONE.sub(_mask_phone, text)
    text = _EMAIL.sub(_mask_email, text)
    return text


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: (_mask_value(v) if k.lower() in _SENSITIVE_KEYS else v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(v) for v in value]
    return value


def mask_result(payload: Any) -> Any:
    """Mask a tool result payload (text / dict / list)."""
    if isinstance(payload, str):
        return mask_text(payload)
    return _mask_value(payload)


def mask_json_string(s: str) -> str:
    try:
        obj = json.loads(s)
        return json.dumps(mask_result(obj), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return mask_text(s)
