"""面向用户的中文展示标签（display layer）。

原则：API/数据库保留 canonical 英文值；这里只生成 *_label 字段，
前端展示必须优先使用 label，不能直接渲染 raw code。
"""

from __future__ import annotations

import copy

DOC_TYPE_LABELS = {
    "lab_report": "化验单",
    "prescription": "处方",
    "discharge_summary": "出院小结",
    "outpatient_record": "门诊病历",
    "drug_insert": "药品说明书",
    "other": "其他文书",
    "unknown": "未知类型",
    "manual": "手动记录",
}

DOC_STATUS_LABELS = {
    "uploaded": "已上传",
    "awaiting_confirmation": "待确认",
    "needs_retake": "需要重拍",
    "confirmed": "已归档",
    "discarded": "已放弃",
}

RECORD_TYPE_LABELS = {
    "blood_glucose": "血糖",
    "blood_pressure": "血压",
    "heart_rate": "心率",
    "spo2": "血氧",
    "blood_lipid": "血脂",
    "weight": "体重",
}

UNIT_LABELS = {
    "mg": "毫克",
    "毫克": "毫克",
    "g": "克",
    "克": "克",
    "ml": "毫升",
    "毫升": "毫升",
    "kg": "公斤",
    "公斤": "公斤",
    "cm": "厘米",
    "mmHg": "毫米汞柱",
    "mmol/L": "毫摩尔每升",
    "mg/dL": "毫克每分升",
    "umol/L": "微摩尔每升",
    "%": "百分比",
    "片": "片",
    "粒": "粒",
    "袋": "袋",
    "支": "支",
    "单位": "单位",
    "次/分": "次/分",
}

DISEASE_LABELS = {
    "diabetes_type2": "2型糖尿病",
    "hypertension": "高血压",
    "hyperlipidemia": "高脂血症",
    "copd": "慢阻肺",
}

CONTEXT_LABELS = {
    "fasting": "空腹",
    "postprandial": "餐后2小时",
    "random": "随机",
    "bedtime": "睡前",
    "ldl": "低密度脂蛋白",
    "tc": "总胆固醇",
    "tg": "甘油三酯",
    "hdl": "高密度脂蛋白",
}

FREQUENCY_LABELS = {
    "qd": "每日1次",
    "bid": "每日2次",
    "tid": "每日3次",
    "qid": "每日4次",
    "q8h": "每8小时",
    "qn": "睡前",
    "prn": "按需",
}

ROUTE_LABELS = {
    "oral": "口服",
    "topical": "外用",
    "inhalation": "吸入",
    "sublingual": "含服",
    "口服": "口服",
    "外用": "外用",
    "吸入": "吸入",
    "含服": "含服",
}

ABNORMAL_FLAG_LABELS = {
    "H": "偏高",
    "high": "偏高",
    "L": "偏低",
    "low": "偏低",
    "N": "正常",
    "normal": "正常",
}

SEVERITY_LABELS = {
    "info": "提示",
    "warning": "警告",
    "error": "错误",
}

DIAGNOSIS_STATUS_LABELS = {
    "current": "当前",
    "past": "既往",
}

APPOINTMENT_STATUS_LABELS = {
    "pending": "待复诊",
    "done": "已完成",
    "cancelled": "已取消",
}

ALERT_LEVEL_LABELS = {
    "green": "正常",
    "yellow": "需要关注",
    "red": "紧急",
    "orange": "需要关注",
}

ALERT_SOURCE_LABELS = {
    "system": "系统",
    "medication": "用药",
    "appointment": "复诊",
    "health_record": "健康记录",
    "warning_agent": "指标预警",
}

ACTION_TYPE_LABELS = {
    "record_created": "已写入健康记录",
    "reminder_created": "已创建用药提醒",
    "diagnosis_created": "已记录诊断",
    "appointment_created": "已创建复诊安排",
    "patient_updated": "已更新健康档案",
    "navigate": "页面跳转",
    "toast": "提示",
    "safety_alert": "紧急提示",
    "no_action": "无需归档",
}

OCR_ERROR_LABELS = {
    "ocr_engine_unavailable": "OCR 引擎不可用",
    "ocr_empty": "未识别到文字",
    "ocr_no_pages": "未读取到页面",
    "ocr_pdf_render_failed": "PDF 解析失败",
}

OCR_ENGINE_LABELS = {
    "rapidocr": "RapidOCR 本地识别",
    "mock": "演示 OCR",
}


def _lookup(table: dict[str, str], value, fallback: str = "未知") -> str:
    if value is None:
        return fallback
    key = str(value)
    return table.get(key, fallback)


def label_doc_type(value) -> str:
    return _lookup(DOC_TYPE_LABELS, value, "未知类型")


def label_doc_status(value) -> str:
    return _lookup(DOC_STATUS_LABELS, value, "未知状态")


def label_record_type(value) -> str:
    if value is None:
        return "其他指标"
    return _lookup(RECORD_TYPE_LABELS, value, "其他指标")


def label_context(value) -> str:
    return _lookup(CONTEXT_LABELS, value, "未指定")


def label_frequency(value) -> str:
    return _lookup(FREQUENCY_LABELS, value, "按医嘱")


def label_route(value) -> str:
    return _lookup(ROUTE_LABELS, value, "按医嘱")


def label_abnormal_flag(value) -> str:
    if value is None or str(value).strip() == "":
        return "未标注"
    return _lookup(ABNORMAL_FLAG_LABELS, value, "异常")


def label_unit(value) -> str:
    if value is None or str(value).strip() == "":
        return ""
    text = str(value).strip()
    return UNIT_LABELS.get(text, text)


def label_disease(value) -> str:
    return _lookup(DISEASE_LABELS, value, "其他慢病")


def label_severity(value) -> str:
    return _lookup(SEVERITY_LABELS, value, "提示")


def label_diagnosis_status(value) -> str:
    return _lookup(DIAGNOSIS_STATUS_LABELS, value, "未知")


def label_appointment_status(value) -> str:
    return _lookup(APPOINTMENT_STATUS_LABELS, value, "未知")


def label_alert_level(value) -> str:
    return _lookup(ALERT_LEVEL_LABELS, value, "未知")


def label_alert_source(value) -> str:
    return _lookup(ALERT_SOURCE_LABELS, value, "系统")


def label_action_type(value) -> str:
    return _lookup(ACTION_TYPE_LABELS, value, "操作")


def label_ocr_error(value) -> str:
    text = str(value or "")
    for prefix, label in OCR_ERROR_LABELS.items():
        if text == prefix or text.startswith(prefix + ":"):
            return label
    return "识别异常"


def label_ocr_engine(value) -> str:
    return _lookup(OCR_ENGINE_LABELS, value, "本地识别")


def localize_parsed(parsed: dict | None) -> dict | None:
    """为确认页生成中文 label 副本，不改动数据库中的 canonical 值。"""
    if not parsed:
        return parsed
    result = copy.deepcopy(parsed)

    result["doc_type_label"] = label_doc_type(result.get("doc_type"))
    if result.get("status"):
        result["status_label"] = label_doc_status(result["status"])

    for metric in result.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        metric["record_type_label"] = label_record_type(metric.get("record_type"))
        metric["context_label"] = label_context(metric.get("context"))
        metric["abnormal_flag_label"] = label_abnormal_flag(metric.get("abnormal_flag"))
        metric["unit_label"] = label_unit(metric.get("unit"))

    for med in result.get("medications") or []:
        if not isinstance(med, dict):
            continue
        med["frequency_label"] = label_frequency(med.get("frequency"))
        med["route_label"] = label_route(med.get("route"))
        med["dose_unit_label"] = label_unit(med.get("dose_unit"))
        med["timing_note_label"] = med.get("timing_note") or ""

    for warning in result.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        warning["severity_label"] = label_severity(warning.get("severity"))

    ocr_meta = result.get("ocr_meta")
    if isinstance(ocr_meta, dict):
        ocr_meta["engine_label"] = label_ocr_engine(ocr_meta.get("engine"))
        ocr_meta["is_mock_label"] = "演示数据" if ocr_meta.get("is_mock") else "真实识别"
        ocr_meta["error_labels"] = [
            label_ocr_error(error) for error in (ocr_meta.get("errors") or [])
        ]
        ocr_meta["page_type_labels"] = [
            label_doc_type(item) for item in (ocr_meta.get("page_types") or [])
        ]

    return result
