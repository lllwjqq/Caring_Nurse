from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.models import Alert, AlertLevel, CarePlan, FollowUp, HealthRecord, LifestyleLog, User
from app.schemas import (
    DashboardStats,
    HealthRecordCreate,
    HealthRecordCreateResult,
    HealthRecordResponse,
    LifestyleLogCreate,
    LifestyleLogResponse,
    RecordFeedback,
)
from app.services.alert_service import (
    AlertService,
    build_feedback_message,
    get_metric_key,
    get_reference_range,
)
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["健康数据"])


@router.post("/records", response_model=HealthRecordCreateResult)
async def create_health_record(
    data: HealthRecordCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    service = HealthService(db)
    record = await service.create_record(patient, data)
    alert_service = AlertService(db)
    alert = await alert_service.evaluate_record(patient, record)

    metric_key = get_metric_key(record.record_type.value, record.extra_data)
    reference_range = get_reference_range(record.record_type.value, metric_key)
    alert_level = alert.level.value if alert else ("yellow" if record.is_abnormal else "green")
    if not record.is_abnormal and not alert:
        alert_level = "green"

    feedback = RecordFeedback(
        is_abnormal=record.is_abnormal or alert is not None,
        alert_level=alert_level,
        reference_range=reference_range,
        message=build_feedback_message(
            record.record_type.value,
            alert.level if alert else None,
            record.extra_data,
            record.is_abnormal or alert is not None,
        ),
        alert_id=alert.id if alert else None,
    )
    return HealthRecordCreateResult(record=record, feedback=feedback)


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


@router.delete("/records/{record_id}")
async def delete_health_record(
    record_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    service = HealthService(db)
    deleted = await service.delete_record(patient, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


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
