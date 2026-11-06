from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Alert, AlertLevel, Appointment, FollowUp, MedicationReminder, Patient
from app.services.document_labels import label_alert_level, label_alert_source
from app.services.memory_service import MemoryService
from app.services.redis_client import redis_client


async def create_followup_tasks():
    """已停用（规格 §10.6）：随访功能删除，保留函数仅为兼容旧引用，不再注册调度。"""
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
                    "level_label": label_alert_level("green"),
                    "title": "服药提醒",
                    "message": message,
                    "source": "medication",
                    "source_label": label_alert_source("medication"),
                })
            except Exception:
                pass
        await db.commit()


async def dispatch_due_appointments():
    """复诊提醒：提前 3 天 + 当天各提醒一次（复用 Alert/WS 通道）。"""
    try:
        tz = ZoneInfo(settings.app_timezone)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    today = now.date()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Appointment).where(Appointment.status == "pending")
        )
        appointments = result.scalars().all()
        for appointment in appointments:
            due = appointment.due_at
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            due_date = due.astimezone(tz).date()
            if due_date == today:
                kind = "day"
                when = "今天"
            elif due_date == today + timedelta(days=3):
                kind = "3day"
                when = "3 天后"
            else:
                continue

            try:
                fired = await redis_client.set_nx(
                    f"appointment_fired:{appointment.id}:{today}:{kind}", "1", 4 * 24 * 3600
                )
            except Exception:
                fired = True
            if not fired:
                continue

            title = "复诊提醒"
            department = f"{appointment.department}" if appointment.department else ""
            message = f"您{when}有复诊安排：{department}{appointment.title}"
            if appointment.due_at:
                message += f"（{due.astimezone(tz).strftime('%m月%d日 %H:%M')}）"
            db.add(
                Alert(
                    patient_id=appointment.patient_id,
                    level=AlertLevel.green,
                    title=title,
                    message=message,
                    source="appointment",
                )
            )
            try:
                await redis_client.publish_alert(
                    appointment.patient_id,
                    {
                        "id": None,
                        "level": "green",
                        "level_label": label_alert_level("green"),
                        "title": title,
                        "message": message,
                        "source": "appointment",
                        "source_label": label_alert_source("appointment"),
                    },
                )
            except Exception:
                pass
        await db.commit()


async def consolidate_inactive_sessions():
    """每 30 分钟巩固无活动会话（规格 §8）。"""
    async with AsyncSessionLocal() as db:
        try:
            count = await MemoryService(db).consolidate_inactive(idle_minutes=30)
            await db.commit()
            print(f"[memory] consolidated {count} session(s)")
        except Exception as exc:
            print(f"[memory] consolidate failed: {exc}")
