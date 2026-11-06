"""结构化呈现（presentation）与 TTS 文本生成（IO_SPEC §3）。

所有面向用户的 agent 回复都应带 presentation：
summary / key_points / action_items / boundary / tts_text。
reply 仍是全文兜底。
"""

from __future__ import annotations

import re
from typing import Iterable

DEFAULT_BOUNDARY = (
    "如出现胸痛、呼吸困难、意识不清、口角歪斜、剧烈头痛、呕血或黑便，"
    "请立即就医或拨打 120；以上建议不能替代医生诊断。"
)
EMERGENCY_BOUNDARY = "这是紧急情况，请立即拨打 120 或马上就医。"

_DIGITS = "零一二三四五六七八九"
_UNITS = (("千", 1000), ("百", 100), ("十", 10), ("", 1))


def _four_digits(value: int) -> str:
    text = ""
    zero = False
    for unit, base in _UNITS:
        digit = value // base % 10
        if digit == 0:
            if text and not zero:
                zero = True
            continue
        if zero:
            text += "零"
            zero = False
        text += _DIGITS[digit] + unit
    return text


def int_to_chinese(value: int) -> str:
    """把 0~99999 的整数转成中文口语数字。"""
    if value == 0:
        return "零"
    if value < 0:
        return "负" + int_to_chinese(-value)
    if value >= 100000:
        return str(value)
    if value >= 10000:
        high, low = divmod(value, 10000)
        text = _four_digits(high) + "万"
        if low:
            if low < 1000:
                text += "零"
            text += _four_digits(low)
        return text
    return _four_digits(value)


def _number_to_chinese(token: str) -> str:
    if "." in token:
        whole, decimal = token.split(".", 1)
        return int_to_chinese(int(whole)) + "点" + "".join(_DIGITS[int(d)] for d in decimal)
    return int_to_chinese(int(token))


def to_tts_text(text: str) -> str:
    """去符号、单位口语化、数字口语化，生成可朗读文本。"""
    if not text:
        return ""
    value = str(text)
    value = re.sub(r"[#*_`>~|]", "", value)
    value = re.sub(r"(?m)^[ \t]*[-•]\s*", "", value)
    value = re.sub(r"[【】\[\]（）()]", "", value)
    value = value.replace("→", "到").replace("≥", "大于等于").replace("≤", "小于等于")
    value = value.replace("—", "，").replace("–", "，")

    # 单位优先替换，避免数字转换后丢失单位
    value = re.sub(r"mmHg", "毫米汞柱", value, flags=re.I)
    value = re.sub(r"mmol/L", "毫摩尔每升", value, flags=re.I)
    value = re.sub(r"mg/dL", "毫克每分升", value, flags=re.I)
    value = re.sub(r"\bmg\b", "毫克", value, flags=re.I)
    value = re.sub(r"\bml\b", "毫升", value, flags=re.I)
    value = re.sub(r"\bkg\b", "公斤", value, flags=re.I)
    value = re.sub(r"\bcm\b", "厘米", value, flags=re.I)
    value = value.replace("℃", "度").replace("SpO2", "血氧").replace("SpO₂", "血氧")
    value = (
        value.replace("LDL-C", "低密度脂蛋白胆固醇")
        .replace("HDL-C", "高密度脂蛋白胆固醇")
        .replace("HbA1c", "糖化血红蛋白")
        .replace("BMI", "体重指数")
    )

    # 血压 140/90 → 一百四十比九十
    value = re.sub(
        r"(\d{2,3})\s*[/／]\s*(\d{2,3})",
        lambda m: f"{int_to_chinese(int(m.group(1)))}比{int_to_chinese(int(m.group(2)))}",
        value,
    )
    # 百分比
    value = re.sub(
        r"(\d+(?:\.\d+)?)\s*%",
        lambda m: "百分之" + _number_to_chinese(m.group(1)),
        value,
    )
    # 普通小数/整数
    value = re.sub(
        r"\d+(?:\.\d+)?",
        lambda m: _number_to_chinese(m.group(0)),
        value,
    )

    value = re.sub(r"[ \t]+", "", value)
    value = re.sub(r"\n+", "。", value)
    value = re.sub(r"[，,；;]+", "。", value)
    value = re.sub(r"。+", "。", value).strip()
    if value and not value.endswith(("。", "！", "？")):
        value += "。"
    return value


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def summarize_reply(reply: str, max_len: int = 20) -> str:
    """取第一句作结论，超长截断。"""
    text = _clean(reply)
    if not text:
        return ""
    text = re.sub(r"^[【\[].*?[】\]]", "", text).strip()
    first = re.split(r"[。！？\n]", text)[0].strip()
    first = re.sub(r"^[，,、；;：:]+", "", first)
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip("，,、；;：:") + "…"
    return first


def _sentences(reply: str) -> list[str]:
    text = _clean(reply)
    text = re.sub(r"^[【\[].*?[】\]]", "", text)
    parts = [p.strip(" ，,、；;：:") for p in re.split(r"[。！？\n]", text)]
    return [p for p in parts if p]


def extract_key_points(reply: str, max_items: int = 3) -> list[str]:
    points: list[str] = []
    for sentence in _sentences(reply):
        if len(sentence) < 4:
            continue
        if any(sentence == p or sentence in p for p in points):
            continue
        points.append(sentence)
        if len(points) >= max_items:
            break
    return points


_ACTION_HINTS = ("建议", "请", "记得", "可以", "需要", "要", "按时", "监测", "复查", "就医", "拨打", "联系", "确认")


def extract_action_items(reply: str, max_items: int = 2) -> list[str]:
    items: list[str] = []
    for sentence in _sentences(reply):
        if not any(word in sentence for word in _ACTION_HINTS):
            continue
        if any(sentence == p or sentence in p for p in items):
            continue
        items.append(sentence)
        if len(items) >= max_items:
            break
    return items


def build_presentation(
    agent: str,
    reply: str,
    *,
    summary: str | None = None,
    key_points: Iterable[str] | None = None,
    action_items: Iterable[str] | None = None,
    boundary: str | None = None,
    tts_text: str | None = None,
    emergency: bool = False,
) -> dict:
    """构造 presentation；字段为空时按 reply 自动兜底。"""
    clean_reply = _clean(reply)
    final_summary = _clean(summary or summarize_reply(clean_reply))[:20]
    points = [_clean(p) for p in (key_points or []) if _clean(p)][:3]
    if not points:
        points = extract_key_points(clean_reply, 3)
    actions = [_clean(a) for a in (action_items or []) if _clean(a)][:2]
    if not actions:
        actions = extract_action_items(clean_reply, 2)
    if not actions:
        actions = ["有变化及时就医"]

    final_boundary = _clean(boundary or (EMERGENCY_BOUNDARY if emergency else DEFAULT_BOUNDARY))
    final_tts = to_tts_text(tts_text) if tts_text else to_tts_text(clean_reply)
    if not final_tts:
        final_tts = to_tts_text(f"{final_summary}。{actions[0]}。")

    return {
        "summary": final_summary,
        "key_points": points,
        "action_items": actions,
        "boundary": final_boundary,
        "tts_text": final_tts,
    }
