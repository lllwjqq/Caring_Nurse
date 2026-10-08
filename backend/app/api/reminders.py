"""服药提醒 CRUD + 今日列表。"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.models import MedicationReminder, User
from app.schemas import (
    MedicationReminderCreate,
    MedicationReminderResponse,
    MedicationReminderUpdate,
)
from app.services.reminder_service import ReminderService

router = APIRouter(prefix="/reminders", tags=["服药提醒"])


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


@router.get("/today", response_model=list[MedicationReminderResponse])
async def today_reminders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient = await get_patient_for_user(user, db)
    today = date.today()
    reminders = await ReminderService(db).list(patient.id)
    return [
        r
        for r in reminders
        if r.active
        and (r.times_of_day or [])
        and (r.start_date is None or r.start_date <= today)
        and (r.end_date is None or r.end_date >= today)
    ]
