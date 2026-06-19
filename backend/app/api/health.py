from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.models import Alert, AlertLevel, CarePlan, FollowUp, HealthRecord, LifestyleLog, User
from app.schemas import (
    DashboardStats,
    HealthRecordCreate,
    HealthRecordResponse,
    LifestyleLogCreate,
    LifestyleLogResponse,
)
from app.services.alert_service import AlertService
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["健康数据"])


@router.post("/records", response_model=HealthRecordResponse)
async def create_health_record(
    data: HealthRecordCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    service = HealthService(db)
    record = await service.create_record(patient, data)
    alert_service = AlertService(db)
    await alert_service.evaluate_record(patient, record)
    return record


@router.get("/records", response_model=list[HealthRecordResponse])
async def list_health_records(
    record_type: str | None = None,
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(HealthRecord)
        .where(HealthRecord.patient_id == patient.id, HealthRecord.recorded_at >= since)
        .order_by(desc(HealthRecord.recorded_at))
    )
    if record_type:
        query = query.where(HealthRecord.record_type == record_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/lifestyle", response_model=LifestyleLogResponse)
async def create_lifestyle_log(
    data: LifestyleLogCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    service = HealthService(db)
    return await service.create_lifestyle_log(patient, data)


@router.get("/lifestyle", response_model=list[LifestyleLogResponse])
async def list_lifestyle_logs(
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(LifestyleLog)
        .where(LifestyleLog.patient_id == patient.id, LifestyleLog.logged_at >= since)
        .order_by(desc(LifestyleLog.logged_at))
    )
    return result.scalars().all()


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    today_result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.patient_id == patient.id, HealthRecord.recorded_at >= today_start)
        .order_by(desc(HealthRecord.recorded_at))
    )
    today_records = today_result.scalars().all()

    alerts_result = await db.execute(
        select(Alert)
        .where(Alert.patient_id == patient.id, Alert.is_resolved == False)
        .order_by(desc(Alert.created_at))
        .limit(5)
    )
    recent_alerts = alerts_result.scalars().all()

    plan_result = await db.execute(
        select(CarePlan)
        .where(CarePlan.patient_id == patient.id, CarePlan.status == "active")
        .order_by(desc(CarePlan.created_at))
        .limit(1)
    )
    active_plan = plan_result.scalar_one_or_none()

    followup_result = await db.execute(
        select(func.count())
        .select_from(FollowUp)
        .where(FollowUp.patient_id == patient.id, FollowUp.status == "pending")
    )
    pending_followups = followup_result.scalar() or 0

    service = HealthService(db)
    trends = await service.get_trends(patient.id)

    risk_level = "green"
    if recent_alerts:
        level_order = {AlertLevel.red: 4, AlertLevel.orange: 3, AlertLevel.yellow: 2, AlertLevel.green: 1}
        risk_level = max(recent_alerts, key=lambda a: level_order.get(a.level, 0)).level.value

    return DashboardStats(
        today_records=today_records,
        recent_alerts=recent_alerts,
        active_plan=active_plan,
        pending_followups=pending_followups,
        risk_level=risk_level,
        trends=trends,
    )
