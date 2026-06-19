from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertLevel, HealthRecord, LifestyleLog, Patient, RecordType
from app.schemas import HealthRecordCreate, LifestyleLogCreate
from app.services.alert_service import AlertService


class HealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_record(self, patient: Patient, data: HealthRecordCreate) -> HealthRecord:
        alert_service = AlertService(self.db)
        is_abnormal, _ = await alert_service.check_threshold(
            patient.diseases or [],
            data.record_type.value,
            data.value,
            data.extra_data,
        )
        record = HealthRecord(
            patient_id=patient.id,
            record_type=data.record_type,
            value=data.value,
            unit=data.unit,
            extra_data=data.extra_data,
            recorded_at=data.recorded_at or datetime.now(timezone.utc),
            is_abnormal=is_abnormal,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def create_lifestyle_log(self, patient: Patient, data: LifestyleLogCreate) -> LifestyleLog:
        log = LifestyleLog(
            patient_id=patient.id,
            log_type=data.log_type,
            content=data.content,
            extra_data=data.extra_data,
            logged_at=data.logged_at or datetime.now(timezone.utc),
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_trends(self, patient_id: int, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(HealthRecord)
            .where(HealthRecord.patient_id == patient_id, HealthRecord.recorded_at >= since)
            .order_by(HealthRecord.recorded_at)
        )
        records = result.scalars().all()
        trends: dict = {}
        for r in records:
            key = r.record_type.value
            if key not in trends:
                trends[key] = []
            point = {"date": r.recorded_at.isoformat(), "value": r.value, "unit": r.unit}
            if r.extra_data:
                point.update(r.extra_data)
            trends[key].append(point)
        return trends

    async def get_recent_records(self, patient_id: int, limit: int = 10) -> list[HealthRecord]:
        result = await self.db.execute(
            select(HealthRecord)
            .where(HealthRecord.patient_id == patient_id)
            .order_by(desc(HealthRecord.recorded_at))
            .limit(limit)
        )
        return list(result.scalars().all())
