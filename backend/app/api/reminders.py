"""服药提醒 CRUD + 今日列表 + 服药打卡（规格附录 A.1）。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import MedicationReminder, User
from app.schemas import (
    MedicationCheckin,
    MedicationReminderCreate,
    MedicationReminderResponse,
    MedicationReminderTodayResponse,
    MedicationReminderUpdate,
)
from app.services.reminder_service import ReminderService

router = APIRouter(prefix="/reminders", tags=["服药提醒"])

VALID_CHECK_STATUS = {"taken", "skipped"}


def _today() -> date:
    try:
        tz = ZoneInfo(settings.app_timezone)
    except Exception:
        tz = None
    return datetime.now(tz).date() if tz else datetime.now().date()


def _parse_date(value: str | None) -> date:
    if not value:
        return _today()
    try:
        return date.fromisoformat(value)
    except Exception:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")


async def _get_reminder(db: AsyncSession, patient_id: int, reminder_id: int) -> MedicationReminder:
    result = await db.execute(
        select(MedicationReminder).where(
            MedicationReminder.id == reminder_id,
            MedicationReminder.patient_id == patient_id,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(404, "提醒不存在")
    return reminder


@router.get("", response_model=list[MedicationReminderResponse])
async def list_reminders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient = await get_patient_for_user(user, db)
    return await ReminderService(db).list(patient.id)


@router.post("", response_model=MedicationReminderResponse)
async def create_reminder(
    data: MedicationReminderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    return await ReminderService(db).create(patient.id, data)


@router.patch("/{reminder_id}", response_model=MedicationReminderResponse)
async def update_reminder(
    reminder_id: int,
    data: MedicationReminderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    reminder = await _get_reminder(db, patient.id, reminder_id)
    return await ReminderService(db).update(reminder, data)


@router.delete("/{reminder_id}")
async def delete_reminder(
    reminder_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    reminder = await _get_reminder(db, patient.id, reminder_id)
    await ReminderService(db).delete(reminder)
    return {"ok": True}


@router.get("/today", response_model=list[MedicationReminderTodayResponse])
async def today_reminders(
    on_date: str | None = Query(default=None, alias="date"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """今日有效提醒 + 当日打卡状态（附录 A.1）。"""
    patient = await get_patient_for_user(user, db)
    target = _parse_date(on_date)
    service = ReminderService(db)
    reminders = await service.list(patient.id)
    checks = await service.get_checks(patient.id, target)

    result: list[MedicationReminderTodayResponse] = []
    for r in reminders:
        if not r.active or not (r.times_of_day or []):
            continue
        if r.start_date and r.start_date > target:
            continue
        if r.end_date and r.end_date < target:
            continue
        base = MedicationReminderResponse.model_validate(r).model_dump()
        result.append(MedicationReminderTodayResponse(**base, checks=checks.get(r.id, {})))
    return result


@router.post("/{reminder_id}/checkin")
async def checkin_reminder(
    reminder_id: int,
    data: MedicationCheckin,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """打卡 / 修改打卡状态；同一「提醒×日期×时间点」重复提交按更新处理。"""
    patient = await get_patient_for_user(user, db)
    reminder = await _get_reminder(db, patient.id, reminder_id)
    if data.status not in VALID_CHECK_STATUS:
        raise HTTPException(400, "status 只能是 taken 或 skipped")
    if data.slot not in (reminder.times_of_day or []):
        raise HTTPException(400, "该时间点不在提醒计划中")

    target = _parse_date(data.date)
    log = await ReminderService(db).checkin(reminder, target, data.slot, data.status)
    return {
        "ok": True,
        "date": target.isoformat(),
        "slot": log.time_of_day,
        "status": log.status,
    }


@router.delete("/{reminder_id}/checkin")
async def uncheckin_reminder(
    reminder_id: int,
    slot: str = Query(...),
    on_date: str | None = Query(default=None, alias="date"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销打卡（用于「已跳过 → 撤销」）。"""
    patient = await get_patient_for_user(user, db)
    reminder = await _get_reminder(db, patient.id, reminder_id)
    target = _parse_date(on_date)
    removed = await ReminderService(db).remove_checkin(reminder, target, slot)
    return {"ok": True, "removed": removed}
