from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Alert, AlertLevel, FollowUp, MedicationReminder, Patient
from app.services.redis_client import redis_client


async def create_followup_tasks():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Patient))
        patients = result.scalars().all()
        for patient in patients:
            existing = await db.execute(
                select(FollowUp).where(
                    FollowUp.patient_id == patient.id,
                    FollowUp.status == "pending",
                )
            )
            if existing.scalar_one_or_none():
                continue
            followup = FollowUp(
                patient_id=patient.id,
                title="每周慢病管理随访",
                questions=[
                    {"id": "q1", "text": "本周是否按时服药？", "type": "boolean"},
                    {"id": "q2", "text": "监测指标频率？", "type": "choice", "options": ["每天", "每周", "很少"]},
                    {"id": "q3", "text": "方案执行评分(1-5)", "type": "scale", "min": 1, "max": 5},
                ],
                status="pending",
                due_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(followup)
        await db.commit()


async def dispatch_due_reminders():
    """每分钟检查到点的服药提醒，生成服药通知（Alert + 实时推送）。"""
    try:
        tz = ZoneInfo(settings.app_timezone)
    except Exception:
        tz = None
    now = datetime.now(tz)
    hhmm = now.strftime("%H:%M")
    today = now.date()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MedicationReminder).where(MedicationReminder.active.is_(True))
        )
        reminders = result.scalars().all()
        for r in reminders:
            if hhmm not in (r.times_of_day or []):
                continue
            if r.start_date and r.start_date > today:
                continue
            if r.end_date and r.end_date < today:
                continue

            # 用 redis SET NX 去重，防止同一分钟重复触发；redis 不可用时放行（宁可重复）
            try:
                fired = await redis_client.set_nx(f"reminder_fired:{r.id}:{today}:{hhmm}", "1", 90)
            except Exception:
                fired = True
            if not fired:
                continue

            dose = f"{r.dose or ''}{r.dose_unit or ''}".strip()
            message = f"请服用 {r.medication_name}" + (f" {dose}" if dose else "")
            if r.timing_note:
                message += f"（{r.timing_note}）"

            db.add(Alert(
                patient_id=r.patient_id,
                level=AlertLevel.green,
                title="服药提醒",
                message=message,
                source="medication",
            ))
            try:
                await redis_client.publish_alert(r.patient_id, {
                    "id": None,
                    "level": "green",
                    "title": "服药提醒",
                    "message": message,
                })
            except Exception:
                pass
        await db.commit()
