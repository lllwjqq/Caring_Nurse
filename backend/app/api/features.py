import io
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.models import Alert, CarePlan, FollowUp, MedicalDocument, User
from app.schemas import (
    AlertResponse,
    CarePlanResponse,
    FollowUpResponse,
    FollowUpSubmit,
    MedicalDocumentResponse,
)
from app.services.alert_service import AlertService
from app.services.storage_service import StorageService

router = APIRouter(tags=["业务功能"])


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    unresolved_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    svc = AlertService(db)
    return await svc.list_alerts(patient.id, unresolved_only)


@router.patch("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.patient_id == patient.id))
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(404, "预警不存在")
    alert.is_read = True
    return {"message": "已标记已读"}


@router.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.patient_id == patient.id))
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(404, "预警不存在")
    alert.is_resolved = True
    return {"message": "已处理"}


@router.get("/care-plans", response_model=list[CarePlanResponse])
async def list_care_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(CarePlan).where(CarePlan.patient_id == patient.id).order_by(CarePlan.created_at.desc())
    )
    return result.scalars().all()


@router.get("/follow-ups", response_model=list[FollowUpResponse])
async def list_followups(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(FollowUp).where(FollowUp.patient_id == patient.id).order_by(FollowUp.created_at.desc())
    )
    return result.scalars().all()


@router.post("/follow-ups/{followup_id}/submit", response_model=FollowUpResponse)
async def submit_followup(
    followup_id: int,
    data: FollowUpSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(FollowUp).where(FollowUp.id == followup_id, FollowUp.patient_id == patient.id)
    )
    followup = result.scalar_one_or_none()
    if not followup:
        from fastapi import HTTPException
        raise HTTPException(404, "随访任务不存在")
    followup.responses = data.responses
    followup.status = "completed"
    followup.completed_at = datetime.now(timezone.utc)
    score = data.responses.get("q3", 3)
    if isinstance(score, (int, float)):
        followup.adherence_score = float(score) / 5.0
    await db.flush()
    return followup


@router.post("/documents/upload", response_model=MedicalDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_for_user(user, db)
    storage = StorageService()
    content = await file.read()
    file_path = await storage.upload(file.filename or "report.pdf", io.BytesIO(content))

    ocr_text, parsed = await storage.process_document(content, file.filename or "")

    doc = MedicalDocument(
        patient_id=patient.id,
        filename=file.filename or "unknown",
        file_path=file_path,
        ocr_text=ocr_text,
        parsed_data=parsed,
        status="processed",
    )
    db.add(doc)
    await db.flush()
    return doc


@router.get("/documents", response_model=list[MedicalDocumentResponse])
async def list_documents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient = await get_patient_for_user(user, db)
    result = await db.execute(
        select(MedicalDocument).where(MedicalDocument.patient_id == patient.id).order_by(MedicalDocument.created_at.desc())
    )
    return result.scalars().all()
