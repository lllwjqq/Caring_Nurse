"""文档处理编排与动作分发。

process：OCR → 分类 → 结构化抽取（纯文本处理，无 DB）。
dispatch：根据 doc_type 把已确认的结构化实体分发到下游（写健康记录/预警等）。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Diagnosis, MedicalDocument, Patient, RecordType
from app.schemas import HealthRecordCreate, MedicationReminderCreate
from app.services.alert_service import AlertService
from app.services.document_parser import (
    CORE_RECORD_TYPES,
    _classify_keywords,
    build_medical_record_modules,
    classify_document,
    extract_structured,
    normalise_parsed,
    validate_parsed,
)
from app.services.health_service import HealthService
from app.services.ocr_service import OCRService
from app.services.reminder_service import ReminderService

VALID_RECORD_TYPES = {e.value for e in RecordType}


class DocumentService:
    def __init__(self, db: AsyncSession | None = None):
        self.ocr = OCRService()
        self.db = db

    async def process(self, content: bytes, filename: str) -> tuple[str, dict]:
        """返回 (ocr_text, parsed)。parsed 含 doc_type / confidence / 实体。"""
        ocr = await self.ocr.extract(content, filename)
        text = ocr.text
        doc_type = await classify_document(text) if text.strip() else "other"
        parsed = await extract_structured(doc_type, text)
        parsed = normalise_parsed(doc_type, parsed)

        page_types = [
            _classify_keywords(page)
            for page in ocr.pages
            if page.strip()
        ]
        parsed["ocr_meta"] = {
            "engine": ocr.engine,
            "is_mock": ocr.is_mock,
            "confidence": ocr.confidence,
            "empty": ocr.empty,
            "errors": ocr.errors,
            "page_count": len(ocr.pages),
            "page_types": page_types,
        }
        parsed = validate_parsed(doc_type, parsed, parsed["ocr_meta"], text)

        warnings = parsed.setdefault("warnings", [])
        distinct_types = {t for t in page_types if t != "other"}
        if len(distinct_types) > 1:
            parsed["mixed_documents"] = True
            warnings.append({
                "code": "mixed_documents",
                "message": "这份文件含多种单据，建议分开上传；当前按最可能的类型处理",
                "field": None,
                "severity": "warning",
            })
        elif any(self._page_looks_mixed(page) for page in ocr.pages if page.strip()):
            parsed["multi_document_page"] = True
            warnings.append({
                "code": "multi_document_page",
                "message": "这一页可能包含多种单据，建议拆开上传",
                "field": None,
                "severity": "warning",
            })

        if doc_type in ("discharge_summary", "outpatient_record"):
            parsed["modules"] = build_medical_record_modules(parsed, doc_type)
        if doc_type in ("other", "prescription", "drug_insert"):
            # 拍药盒降级：只做 OCR 文字 → Drug 库匹配，不做图片/条码识别
            parsed["drug_matches"] = await self._match_drugs(text)
            parsed["manual_input_required"] = not parsed["drug_matches"]

        parsed["status"] = "needs_retake" if parsed.get("needs_retake") else "awaiting_confirmation"
        return text, parsed

    @staticmethod
    def _page_looks_mixed(page: str) -> bool:
        prescription = any(k in page for k in ("处方", "Rp", "用法用量"))
        lab = any(k in page for k in ("检验", "化验", "参考范围", "mmol", "mmHg", "项目"))
        return prescription and lab

    async def _match_drugs(self, text: str) -> list[dict]:
        if not self.db:
            return []
        from sqlalchemy import select

        from app.models import Drug

        result = await self.db.execute(select(Drug))
        matches: list[dict] = []
        for drug in result.scalars().all():
            names = [drug.generic_name] + list(getattr(drug, "brand_names", None) or [])
            if any(name and str(name) in text for name in names):
                matches.append(
                    {
                        "name": drug.generic_name,
                        "brand_names": getattr(drug, "brand_names", None) or [],
                        "spec": getattr(drug, "spec", None),
                    }
                )
            if len(matches) >= 5:
                break
        return matches

    async def dispatch(
        self,
        db: AsyncSession,
        patient: Patient,
        doc_type: str,
        entities: dict,
        source_document_id: int | None = None,
    ) -> list[dict]:
        """把用户已确认的实体分发到下游，返回动作摘要列表。"""
        if doc_type == "lab_report":
            return await self._dispatch_lab_report(db, patient, entities, source_document_id)
        if doc_type == "prescription":
            return await self._dispatch_prescription(db, patient, entities, source_document_id)
        if doc_type in ("discharge_summary", "outpatient_record"):
            return await self._dispatch_medical_record(db, patient, doc_type, entities, source_document_id)
        return [{"type": "no_action", "summary": "该文档类型暂不支持自动归档，已保存识别原文"}]

    async def _dispatch_lab_report(
        self, db, patient, entities, source_document_id: int | None
    ) -> list[dict]:
        metrics = entities.get("metrics") or []
        recorded_at = self._parse_doc_date(
            entities.get("document_date") or entities.get("exam_date")
        )
        actions: list[dict] = []
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            record_type = metric.get("record_type")
            if record_type not in CORE_RECORD_TYPES:
                continue  # 非核心指标只留在 parsed_data
            value = metric.get("value")
            if value is None:
                continue
            extra_data: dict = {}
            try:
                if record_type == "blood_pressure":
                    systolic = metric.get("systolic")
                    diastolic = metric.get("diastolic")
                    if systolic is None or diastolic is None or float(systolic) < float(diastolic):
                        continue
                    value = float(systolic)
                    extra_data["systolic"] = float(systolic)
                    extra_data["diastolic"] = float(diastolic)
                else:
                    value = float(value)
                if record_type in ("blood_glucose", "blood_lipid") and metric.get("context"):
                    extra_data["type"] = metric["context"]
            except (TypeError, ValueError):
                continue

            try:
                record = await HealthService(db).create_record(
                    patient,
                    HealthRecordCreate(
                        record_type=RecordType(record_type),
                        value=value,
                        unit=metric.get("unit") or "",
                        extra_data=extra_data,
                        recorded_at=recorded_at,
                    ),
                )
                record.source_document_id = source_document_id
                await AlertService(db).evaluate_record(patient, record)
            except Exception:
                continue

            name = metric.get("name") or record_type
            display = f"{value}"
            if record_type == "blood_pressure" and extra_data.get("diastolic") is not None:
                display = f"{extra_data['systolic']}/{extra_data['diastolic']}"
            actions.append({
                "type": "record_created",
                "record_id": record.id,
                "summary": f"已记录{name} {display}{metric.get('unit') or ''}",
            })

        if not actions:
            actions.append({"type": "no_action", "summary": "未识别到可归档的核心指标"})
        return actions

    async def _dispatch_prescription(
        self, db, patient, entities, source_document_id: int | None
    ) -> list[dict]:
        doc_date = entities.get("document_date") or entities.get("issue_date")
        actions = await self._create_diagnoses(
            db, patient, entities.get("diagnoses") or [], "prescription", doc_date, source_document_id
        )
        actions += await self._create_reminders(
            db, patient, entities.get("medications") or [], source_document_id, doc_date
        )
        if not actions:
            actions.append({"type": "no_action", "summary": "未识别到可归档的处方信息"})
        return actions

    async def _dispatch_medical_record(
        self, db, patient, doc_type: str, entities, source_document_id: int | None
    ) -> list[dict]:
        doc_date = entities.get("document_date")
        actions = await self._create_diagnoses(
            db, patient, entities.get("diagnoses") or [], doc_type, doc_date, source_document_id
        )
        actions += await self._create_reminders(
            db, patient, entities.get("medications") or [], source_document_id, doc_date
        )

        followup_at = self._parse_doc_date(entities.get("followup_at"))
        if followup_at:
            department = entities.get("followup_department")
            title = f"{department}复诊" if department else "复诊"
            appointment = Appointment(
                patient_id=patient.id,
                title=title,
                department=department,
                due_at=followup_at,
                source_document_id=source_document_id,
                status="pending",
            )
            db.add(appointment)
            await db.flush()
            actions.append({
                "type": "appointment_created",
                "appointment_id": appointment.id,
                "summary": f"已创建复诊安排：{title}（{followup_at.date().isoformat()}）",
            })

        changed = self._merge_patient_history(
            patient,
            allergies=entities.get("allergies"),
            family_history=entities.get("family_history"),
            personal_history=entities.get("personal_history"),
        )
        if changed:
            actions.append({"type": "patient_updated", "summary": "已更新过敏史/家族史"})

        if not actions:
            actions.append({"type": "no_action", "summary": "未识别到可归档的病历信息"})
        return actions

    async def _create_diagnoses(
        self, db, patient, names, doc_type: str, document_date, source_document_id: int | None
    ) -> list[dict]:
        diagnosed_at = self._parse_doc_date(document_date)
        actions: list[dict] = []
        for name in names:
            text = str(name).strip()
            if not text:
                continue
            diagnosis = Diagnosis(
                patient_id=patient.id,
                name=text,
                diagnosed_at=diagnosed_at,
                doc_type=doc_type,
                source_document_id=source_document_id,
                status="current",
            )
            db.add(diagnosis)
            await db.flush()
            actions.append({
                "type": "diagnosis_created",
                "diagnosis_id": diagnosis.id,
                "summary": f"已记录诊断：{text}",
            })
        return actions

    async def _create_reminders(
        self, db, patient, medications, source_document_id: int | None, document_date
    ) -> list[dict]:
        actions: list[dict] = []
        start_date = self._parse_doc_date(document_date)
        for med in medications:
            if not isinstance(med, dict):
                continue
            name = str(med.get("generic_name") or med.get("name") or "").strip()
            if not name:
                continue
            dose, dose_unit = self._split_dose(med.get("dose"), med.get("dose_unit"))
            frequency = self._normalise_frequency(med.get("frequency"))
            end_date = None
            duration = med.get("duration_days")
            if duration and start_date:
                try:
                    end_date = start_date.date() + timedelta(days=int(duration))
                except (TypeError, ValueError):
                    end_date = None
            try:
                reminder = await ReminderService(db).create(
                    patient.id,
                    MedicationReminderCreate(
                        medication_name=name,
                        brand_name=med.get("brand_name"),
                        spec=med.get("spec"),
                        dose=dose,
                        dose_unit=dose_unit,
                        frequency=frequency,
                        route=med.get("route"),
                        timing_note=med.get("timing_note"),
                        start_date=start_date.date().isoformat() if start_date else None,
                        end_date=end_date.isoformat() if end_date else None,
                        notes=med.get("notes") or med.get("note"),
                    ),
                    source_document_id=source_document_id,
                )
            except Exception:
                continue
            dose_str = f"{dose or ''}{dose_unit or ''}".strip() or "按医嘱"
            times_str = "、".join(reminder.times_of_day or []) or "按需"
            actions.append({
                "type": "reminder_created",
                "reminder_id": reminder.id,
                "summary": f"已创建服药提醒：{name} {dose_str}（每日 {times_str}）",
            })
        return actions

    @staticmethod
    def _split_dose(value, unit) -> tuple[float | None, str | None]:
        if value is None:
            return None, unit
        if isinstance(value, (int, float)):
            return float(value), unit
        text = str(value).strip()
        if not text:
            return None, unit
        import re

        match = re.match(r"(\d+(?:\.\d+)?)\s*(mg|g|片|粒|ml|毫升|袋|支|单位)?", text, re.I)
        if not match:
            return None, unit
        return float(match.group(1)), (unit or match.group(2))

    @staticmethod
    def _normalise_frequency(value) -> str:
        text = str(value or "qd").strip().lower()
        mapping = {
            "每日1次": "qd", "每日一次": "qd", "每天一次": "qd",
            "每日2次": "bid", "每日两次": "bid", "每天两次": "bid",
            "每日3次": "tid", "每日三次": "tid", "每天三次": "tid",
            "每日4次": "qid", "每日四次": "qid", "每天四次": "qid",
            "睡前": "qn", "按需": "prn",
        }
        if text in mapping:
            return mapping[text]
        if text in {"qd", "bid", "tid", "qid", "q8h", "qn", "prn"}:
            return text
        return "qd"

    @staticmethod
    def _merge_patient_history(
        patient: Patient,
        *,
        allergies=None,
        family_history=None,
        personal_history=None,
    ) -> bool:
        import re

        changed = False
        raw_allergies = str(allergies or "").strip()
        if raw_allergies and not any(w in raw_allergies for w in ("否认", "无过敏", "未见")):
            existing = [
                p.strip()
                for p in re.split(r"[、,，;；\s]+", patient.allergies or "")
                if p.strip()
            ]
            for item in re.split(r"[、,，;；\s]+", raw_allergies):
                item = item.strip()
                if item and item not in existing:
                    existing.append(item)
            merged = "、".join(existing)
            if merged != (patient.allergies or ""):
                patient.allergies = merged
                changed = True

        profile = dict(patient.health_profile or {})
        for key, value in (("family_history", family_history), ("personal_history", personal_history)):
            text = str(value or "").strip()
            if not text:
                continue
            if profile.get(key) != text:
                profile[key] = text
                changed = True
        if changed:
            patient.health_profile = profile
        return changed

    @staticmethod
    def _parse_doc_date(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if d.tzinfo is None:
            d = d.replace(hour=9, minute=0, second=0, tzinfo=timezone.utc)
        return d

    @staticmethod
    def _parse_exam_date(exam_date) -> datetime | None:
        return DocumentService._parse_doc_date(exam_date)
