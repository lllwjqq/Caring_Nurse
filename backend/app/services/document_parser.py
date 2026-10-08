"""医疗文档分类与结构化抽取。

分类器把 OCR 原文归入 doc_type；抽取器按 doc_type 走对应的 schema，
优先用 LLM structured output，失败/不可用时回退到正则模板（仅化验单）。

新增一种文档类型 = 在这里登记一个 doc_type + 一套抽取逻辑，
动作分发见 document_processing.py。
"""

import re

from app.config import settings
from app.services.llm_service import llm_service

# 指标名 → 展示名
RECORD_TYPE_LABELS = {
    "blood_glucose": "血糖",
    "blood_pressure": "血压",
    "heart_rate": "心率",
    "spo2": "血氧",
    "blood_lipid": "血脂",
    "weight": "体重",
}

CLASSIFY_SYSTEM = (
    "你是医疗文档分类器。判断用户提供的 OCR 文本属于哪一类，只输出 JSON，"
    '形如 {"doc_type":"lab_report"}。doc_type 取值：'
    "lab_report（体检报告/化验单）、prescription（处方/医嘱）、"
    "discharge_summary（出院小结/诊断证明）、drug_insert（药品说明书）、other。"
    "不要输出任何其他文字。"
)

EXTRACT_LAB_SYSTEM = (
    "你是医疗单据结构化抽取助手。从 OCR 文本中提取体检/化验指标，只输出 JSON，不要其他文字。\n"
    "输出格式：\n"
    '{"doc_type":"lab_report","confidence":0.9,"exam_date":"YYYY-MM-DD 或 null",'
    '"metrics":[{"name":"原指标名","record_type":"...","value":6.8,"unit":"mmol/L",'
    '"context":"fasting","systolic":null,"diastolic":null,"reference":"...",'
    '"abnormal_flag":"H 或 null","confidence":0.95}]}\n'
    "record_type 取值与要求：\n"
    "- blood_glucose 血糖：value 为数值(mmol/L)，context 取 fasting/postprandial/random/bedtime"
    "（对应空腹/餐后2h/随机/睡前，无法判断填 null）\n"
    "- blood_pressure 血压：必须给出 systolic 和 diastolic 两个数值，value 填收缩压\n"
    "- heart_rate 心率：value 数值(次/分)\n"
    "- spo2 血氧：value 数值(%)\n"
    "- blood_lipid 血脂：context 取 ldl/tc/tg/hdl（低密度/总胆固醇/甘油三酯/高密度），value 数值(mmol/L)\n"
    "- weight 体重：value 数值(kg)\n"
    "无法确定的字段填 null，严禁编造数值。无有效指标时 metrics 为空数组。"
)

EXTRACT_PRESCRIPTION_SYSTEM = (
    "你是处方结构化抽取助手。从 OCR 文本中提取处方用药信息，只输出 JSON，不要其他文字。\n"
    "输出格式：\n"
    '{"doc_type":"prescription","confidence":0.9,"hospital":"...或null","department":"...或null",'
    '"doctor":"...或null","issue_date":"YYYY-MM-DD 或 null",'
    '"medications":[{"name":"药名","generic_name":"通用名或null","spec":"规格或null",'
    '"dose":1,"dose_unit":"片/mg/ml或null","frequency":"qd/bid/tid/qid/q8h/qn/prn",'
    '"route":"口服/外用/吸入/含服或null","timing_note":"饭前/饭后/睡前/晨起或null",'
    '"duration_days":7或null,"notes":"注意事项或null","confidence":0.9}]}\n'
    "频次拉丁文缩写：qd=每日1次、bid=每日2次、tid=每日3次、qid=每日4次、q8h=每8小时、qn=睡前、prn=必要时。\n"
    "无法确定的字段填 null，严禁编造。无有效药品时 medications 为空数组。"
)

# 正则回退模板：(pattern, record_type, unit, context)
_LAB_PATTERNS = [
    (r"空腹血糖[：:]\s*([\d.]+)", "blood_glucose", "mmol/L", "fasting"),
    (r"餐后(?:2h|两小时|2小时)?血糖[：:]\s*([\d.]+)", "blood_glucose", "mmol/L", "postprandial"),
    (r"随机血糖[：:]\s*([\d.]+)", "blood_glucose", "mmol/L", "random"),
    (r"睡前血糖[：:]\s*([\d.]+)", "blood_glucose", "mmol/L", "bedtime"),
    (r"血糖[：:]\s*([\d.]+)", "blood_glucose", "mmol/L", None),
    (r"血压[：:]\s*(\d+)\s*/\s*(\d+)", "blood_pressure", "mmHg", None),
    (r"心率[：:]\s*(\d+)", "heart_rate", "次/分", None),
    (r"血氧(?:饱和度)?[：:]\s*(\d+)", "spo2", "%", None),
    (r"总胆固醇[：:]\s*([\d.]+)", "blood_lipid", "mmol/L", "tc"),
    (r"甘油三酯[：:]\s*([\d.]+)", "blood_lipid", "mmol/L", "tg"),
    (r"低密度脂蛋白[：:]\s*([\d.]+)", "blood_lipid", "mmol/L", "ldl"),
    (r"高密度脂蛋白[：:]\s*([\d.]+)", "blood_lipid", "mmol/L", "hdl"),
    (r"体重[：:]\s*([\d.]+)\s*(?:kg|公斤)?", "weight", "kg", None),
]


async def classify_document(text: str) -> str:
    """返回 doc_type。优先 LLM，失败回退关键词。"""
    if llm_service.is_available:
        result = await llm_service.extract_json(CLASSIFY_SYSTEM, text)
        if result and result.get("doc_type"):
            return result["doc_type"]
    return _classify_keywords(text)


def _classify_keywords(text: str) -> str:
    if any(k in text for k in ("处方", "Rp", "用法用量", "遵医嘱", "bid", "tid", "qd")):
        return "prescription"
    if any(k in text for k in ("出院小结", "诊断证明", "入院日期", "出院日期")):
        return "discharge_summary"
    if any(k in text for k in ("说明书", "适应症", "不良反应", "禁忌")):
        return "drug_insert"
    if any(k in text for k in ("血糖", "血压", "化验", "体检报告", "参考", "mmol", "mmHg", "心率", "血氧")):
        return "lab_report"
    return "other"


async def extract_structured(doc_type: str, text: str) -> dict:
    """按 doc_type 抽取结构化实体。返回 {"doc_type","confidence",...}。"""
    if doc_type == "lab_report":
        return await _extract_lab_report(text)
    if doc_type == "prescription":
        return await _extract_prescription(text)
    return {"doc_type": doc_type, "confidence": 0.0, "metrics": []}


async def _extract_prescription(text: str) -> dict:
    if settings.ocr_use_llm_extract and llm_service.is_available:
        result = await llm_service.extract_json(EXTRACT_PRESCRIPTION_SYSTEM, text)
        if isinstance(result, dict) and result.get("medications"):
            result.setdefault("doc_type", "prescription")
            result.setdefault("confidence", 0.5)
            return result
    return _extract_prescription_regex(text)


def _extract_prescription_regex(text: str) -> dict:
    """处方结构复杂、手写/缩写多，正则回退只做最简抽取，通常为空。"""
    return {"doc_type": "prescription", "confidence": 0.3, "medications": []}


async def _extract_lab_report(text: str) -> dict:
    if settings.ocr_use_llm_extract and llm_service.is_available:
        result = await llm_service.extract_json(EXTRACT_LAB_SYSTEM, text)
        if isinstance(result, dict) and result.get("metrics"):
            result.setdefault("doc_type", "lab_report")
            result.setdefault("confidence", 0.5)
            return result
    return _extract_lab_report_regex(text)


def _extract_lab_report_regex(text: str) -> dict:
    metrics: list[dict] = []
    for pattern, rtype, unit, context in _LAB_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        if rtype == "blood_pressure":
            systolic, diastolic = float(m.group(1)), float(m.group(2))
            metrics.append({
                "name": "血压",
                "record_type": rtype,
                "value": systolic,
                "unit": unit,
                "context": context,
                "systolic": systolic,
                "diastolic": diastolic,
                "reference": None,
                "abnormal_flag": None,
                "confidence": 0.7,
            })
        else:
            metrics.append({
                "name": RECORD_TYPE_LABELS.get(rtype, rtype),
                "record_type": rtype,
                "value": float(m.group(1)),
                "unit": unit,
                "context": context,
                "systolic": None,
                "diastolic": None,
                "reference": None,
                "abnormal_flag": None,
                "confidence": 0.7,
            })

    exam_date = None
    dm = re.search(r"检测日期[：:]\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if dm:
        exam_date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

    return {"doc_type": "lab_report", "confidence": 0.7, "exam_date": exam_date, "metrics": metrics}
