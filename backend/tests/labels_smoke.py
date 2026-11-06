"""中文 label 回归：所有面向用户的枚举都不应直接暴露 raw code。"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import AlertLevel, RecordType  # noqa: E402
from app.schemas import (  # noqa: E402
    AlertResponse,
    AppointmentResponse,
    DiagnosisResponse,
    DocumentAction,
    HealthRecordResponse,
    MedicalDocumentResponse,
    MedicationReminderResponse,
)

now = datetime.now(timezone.utc)
ok = True


def check(name: str, actual: str, expected: str) -> None:
    global ok
    passed = actual == expected
    ok = ok and passed
    print("PASS" if passed else "FAIL", name, "actual=", actual)


doc = MedicalDocumentResponse(
    id=1,
    patient_id=1,
    filename="rx.png",
    doc_type="prescription",
    confidence=0.9,
    ocr_text="",
    parsed_data={
        "doc_type": "prescription",
        "metrics": [{"record_type": "blood_pressure", "unit": "mmHg", "context": "fasting", "abnormal_flag": "high"}],
        "medications": [{"frequency": "bid", "route": "oral", "dose_unit": "mg", "timing_note": "饭后"}],
        "warnings": [{"severity": "warning", "message": "low"}],
        "ocr_meta": {"engine": "rapidocr", "is_mock": False, "errors": ["ocr_empty"], "page_types": ["lab_report"]},
    },
    status="awaiting_confirmation",
    created_at=now,
)
check("doc_type_label", doc.doc_type_label, "处方")
check("doc_status_label", doc.status_label, "待确认")
check("metric_record_type_label", doc.parsed_data["metrics"][0]["record_type_label"], "血压")
check("metric_unit_label", doc.parsed_data["metrics"][0]["unit_label"], "毫米汞柱")
check("metric_context_label", doc.parsed_data["metrics"][0]["context_label"], "空腹")
check("metric_flag_label", doc.parsed_data["metrics"][0]["abnormal_flag_label"], "偏高")
check("med_frequency_label", doc.parsed_data["medications"][0]["frequency_label"], "每日2次")
check("med_route_label", doc.parsed_data["medications"][0]["route_label"], "口服")
check("med_unit_label", doc.parsed_data["medications"][0]["dose_unit_label"], "毫克")
check("warning_severity_label", doc.parsed_data["warnings"][0]["severity_label"], "警告")
check("ocr_engine_label", doc.parsed_data["ocr_meta"]["engine_label"], "RapidOCR 本地识别")
check("ocr_error_label", doc.parsed_data["ocr_meta"]["error_labels"][0], "未识别到文字")
check("ocr_page_type_label", doc.parsed_data["ocr_meta"]["page_type_labels"][0], "化验单")

diag = DiagnosisResponse(
    id=1, patient_id=1, name="高血压", diagnosed_at=None,
    doc_type="outpatient_record", source_document_id=None,
    status="current", notes=None, created_at=now,
)
check("diagnosis_doc_label", diag.doc_type_label, "门诊病历")
check("diagnosis_status_label", diag.status_label, "当前")

appt = AppointmentResponse(
    id=1, patient_id=1, title="复诊", department="内科", due_at=now,
    source_document_id=None, status="pending", created_at=now,
)
check("appointment_status_label", appt.status_label, "待复诊")

record = HealthRecordResponse(
    id=1, patient_id=1, record_type=RecordType.blood_pressure, value=140,
    unit="mmHg", extra_data={}, recorded_at=now, is_abnormal=True,
)
check("health_record_label", record.record_type_label, "血压")
check("health_unit_label", record.unit_label, "毫米汞柱")

reminder = MedicationReminderResponse(
    id=1, patient_id=1, medication_name="阿司匹林", brand_name=None, spec="100mg",
    dose=100, dose_unit="mg", frequency="qd", times_of_day=["08:00"],
    route="oral", timing_note="饭后", start_date=None, end_date=None,
    notes=None, source_document_id=None, active=True, created_at=now,
)
check("reminder_frequency_label", reminder.frequency_label, "每日1次")
check("reminder_route_label", reminder.route_label, "口服")
check("reminder_unit_label", reminder.dose_unit_label, "毫克")

alert = AlertResponse(
    id=1, patient_id=1, level=AlertLevel.yellow, title="预警", message="注意",
    source="appointment", suggestion=None, is_read=False, is_resolved=False,
    created_at=now,
)
check("alert_level_label", alert.level_label, "需要关注")
check("alert_source_label", alert.source_label, "复诊")

action = DocumentAction(type="record_created", summary="已记录")
check("action_type_label", action.type_label, "已写入健康记录")

print("OVERALL", "PASS" if ok else "FAIL")
