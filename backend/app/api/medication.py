"""用药安全接口（规格 §10.4）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.patients import get_patient_for_user
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import MedicationSafetyResponse
from app.services.drug_service import DrugSafetyService

router = APIRouter(prefix="/medication", tags=["用药安全"])


@router.get("/safety", response_model=MedicationSafetyResponse)
async def medication_safety(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前患者用药的过敏/相互作用/剂量/重复问题。"""
    patient = await get_patient_for_user(user, db)
    issues = await DrugSafetyService(db).check_patient(patient)
    return MedicationSafetyResponse(issues=issues)
