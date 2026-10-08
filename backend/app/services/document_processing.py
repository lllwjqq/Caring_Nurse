"""文档处理编排与动作分发。

process：OCR → 分类 → 结构化抽取（纯文本处理，无 DB）。
dispatch：根据 doc_type 把已确认的结构化实体分发到下游（写健康记录/预警等）。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MedicalDocument, Patient, RecordType
from app.schemas import HealthRecordCreate, MedicationReminderCreate
from app.services.alert_service import AlertService
from app.services.document_parser import classify_document, extract_structured
from app.services.health_service import HealthService
from app.services.ocr_service import OCRService
from app.services.reminder_service import ReminderService

VALID_RECORD_TYPES = {e.value for e in RecordType}


class DocumentService:
    def __init__(self):
        self.ocr = OCRService()

    async def process(self, content: bytes, filename: str) -> tuple[str, dict]:
        """返回 (ocr_text, parsed)。parsed 含 doc_type / confidence / 实体。"""
        text = await self.ocr.extract_text(content, filename)
        doc_type = await classify_document(text)
        parsed = await extract_structured(doc_type, text)
        return text, parsed

    async def dispatch(
        self, db: AsyncSession, patient: Patient, doc: MedicalDocument, entities: dict
    ) -> list[dict]:
        """把用户已确认的实体分发到下游，返回动作摘要列表。"""
        if doc.doc_type == "lab_report":
            return await self._dispatch_lab_report(db, patient, entities)
        if doc.doc_type == "prescription":
            return await self._dispatch_prescription(db, patient, entities, doc.id)
        return [{"type": "no_action", "summary": "该文档类型暂不支持自动归档，已保存识别原文"}]

    async def _dispatch_lab_report(self, db, patient, entities) -> list[dict]:
        metrics = entities.get("metrics") or []
        recorded_at = self._parse_exam_date(entities.get("exam_date"))
        actions: list[dict] = []
        for m in metrics:
            rtype = m.get("record_type")
            if rtype not in VALID_RECORD_TYPES:
                continue
            value = m.get("value")
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue

            extra_data: dict = {}
            if rtype == "blood_pressure":
                systolic = m.get("systolic")
                diastolic = m.get("diastolic")
                if systolic is not None:
                    value = float(systolic)
                    extra_data["systolic"] = float(systolic)
                if diastolic is not None:
                    extra_data["diastolic"] = float(diastolic)
            elif rtype in ("blood_glucose", "blood_lipid") and m.get("context"):
                extra_data["type"] = m["context"]

            try:
                record = await HealthService(db).create_record(
                    patient,
                    HealthRecordCreate(
                        record_type=RecordType(rtype),
                        value=value,
                        unit=m.get("unit") or "",
                        extra_data=extra_data,
                        recorded_at=recorded_at,
                    ),
                )
                await AlertService(db).evaluate_record(patient, record)
            except Exception:
                continue

            name = m.get("name") or rtype
            display = f"{value}"
            if rtype == "blood_pressure" and extra_data.get("diastolic") is not None:
                display = f"{extra_data['systolic']}/{extra_data['diastolic']}"
            actions.append({
                "type": "record_created",
                "record_id": record.id,
                "summary": f"已记录{name} {display}{m.get('unit') or ''}",
            })

        if not actions:
            actions.append({"type": "no_action", "summary": "未识别到可归档的健康指标"})
        return actions

    async def _dispatch_prescription(
        self, db, patient, entities, source_document_id: int | None
    ) -> list[dict]:
        medications = entities.get("medications") or []
        issue_date = entities.get("issue_date")
        actions: list[dict] = []
        for med in medications:
            name = med.get("generic_name") or med.get("name")
            if not name:
                continue
            end_date = None
            duration = med.get("duration_days")
            if duration and issue_date:
                try:
                    start = datetime.fromisoformat(str(issue_date)).date()
                    end_date = (start + timedelta(days=int(duration))).isoformat()
                except Exception:
                    pass
            try:
                reminder = await ReminderService(db).create(
                    patient.id,
                    MedicationReminderCreate(
                        medication_name=name,
                        brand_name=med.get("brand_name"),
                        spec=med.get("spec"),
                        dose=med.get("dose"),
                        dose_unit=med.get("dose_unit"),
                        frequency=med.get("frequency") or "qd",
                        route=med.get("route"),
                        timing_note=med.get("timing_note"),
                        start_date=issue_date,
                        end_date=end_date,
                        notes=med.get("notes"),
                    ),
                    source_document_id=source_document_id,
                )
            except Exception:
                continue
            dose_str = f"{med.get('dose') or ''}{med.get('dose_unit') or ''}".strip() or "按医嘱"
            times_str = "、".join(reminder.times_of_day or []) or "按需"
            actions.append({
                "type": "reminder_created",
                "reminder_id": reminder.id,
                "summary": f"已创建服药提醒：{name} {dose_str}（每日 {times_str}）",
            })
        if not actions:
            actions.append({"type": "no_action", "summary": "未识别到可用的药品信息"})
        return actions

    @staticmethod
    def _parse_exam_date(exam_date) -> datetime | None:
        if not exam_date:
            return None
        try:
            d = datetime.fromisoformat(str(exam_date).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(hour=9, minute=0, second=0, tzinfo=timezone.utc)
            return d
        except Exception:
            return None
