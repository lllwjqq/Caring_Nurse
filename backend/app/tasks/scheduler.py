from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import FollowUp, Patient


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
