"""服药提醒服务：频次展开、CRUD、到期查询。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MedicationReminder
from app.schemas import MedicationReminderCreate, MedicationReminderUpdate

FREQUENCY_DEFAULT_TIMES: dict[str, list[str]] = {
    "qd": ["08:00"],
    "bid": ["08:00", "20:00"],
    "tid": ["08:00", "12:30", "18:30"],
    "qid": ["08:00", "12:30", "18:00", "22:00"],
    "q8h": ["08:00", "16:00", "00:00"],
    "qn": ["21:00"],
    "prn": [],
}


def expand_times(frequency: str, timing_note: str | None = None) -> list[str]:
    """根据频次 + 服用时点展开成每日服药时间点（HH:MM 列表）。"""
    if frequency == "prn":
        return []
    if timing_note and "睡前" in timing_note:
        return ["21:00"]
    times = list(FREQUENCY_DEFAULT_TIMES.get(frequency, ["08:00"]))
    if timing_note and ("晨起" in timing_note or "早餐前" in timing_note):
        times[0] = "07:30"
    return times


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


class ReminderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        patient_id: int,
        data: MedicationReminderCreate,
        source_document_id: int | None = None,
    ) -> MedicationReminder:
        times = data.times_of_day or expand_times(data.frequency, data.timing_note)
        reminder = MedicationReminder(
            patient_id=patient_id,
            medication_name=data.medication_name,
            brand_name=data.brand_name,
            spec=data.spec,
            dose=data.dose,
            dose_unit=data.dose_unit,
            frequency=data.frequency,
            times_of_day=times,
            route=data.route,
            timing_note=data.timing_note,
            start_date=_parse_date(data.start_date),
            end_date=_parse_date(data.end_date),
            notes=data.notes,
            source_document_id=source_document_id,
            active=True,
        )
        self.db.add(reminder)
        await self.db.flush()
        return reminder

    async def list(self, patient_id: int) -> list[MedicationReminder]:
        result = await self.db.execute(
            select(MedicationReminder)
            .where(MedicationReminder.patient_id == patient_id)
            .order_by(MedicationReminder.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, reminder: MedicationReminder, data: MedicationReminderUpdate) -> MedicationReminder:
        values = data.model_dump(exclude_unset=True)
        for field, value in values.items():
            if field in ("start_date", "end_date"):
                value = _parse_date(value)
            setattr(reminder, field, value)
        # 频次/时点变更后若无显式时间，重算默认服药点
        if "times_of_day" not in values and ("frequency" in values or "timing_note" in values):
            reminder.times_of_day = expand_times(reminder.frequency, reminder.timing_note)
        await self.db.flush()
        return reminder

    async def delete(self, reminder: MedicationReminder) -> None:
        await self.db.delete(reminder)
        await self.db.flush()

    async def get_due(self, patient_id: int, hhmm: str, today: date) -> list[MedicationReminder]:
        result = await self.db.execute(
            select(MedicationReminder).where(
                MedicationReminder.patient_id == patient_id,
                MedicationReminder.active.is_(True),
            )
        )
        reminders = result.scalars().all()
        return [
            r
            for r in reminders
            if hhmm in (r.times_of_day or [])
            and (r.start_date is None or r.start_date <= today)
            and (r.end_date is None or r.end_date >= today)
        ]
