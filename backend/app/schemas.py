from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models import AlertLevel, DiseaseType, LifestyleType, RecordType, UserRole


# Auth
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    agreed_disclaimer: bool = False


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    agreed_disclaimer: bool

    model_config = {"from_attributes": True}


# Patient
class PatientCreate(BaseModel):
    gender: str | None = None
    birth_date: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    diseases: list[str] = []
    allergies: str | None = None
    medications: str | None = None
    emergency_contact: str | None = None


class PatientUpdate(BaseModel):
    gender: str | None = None
    birth_date: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    diseases: list[str] | None = None
    allergies: str | None = None
    medications: str | None = None
    emergency_contact: str | None = None


class PatientResponse(BaseModel):
    id: int
    user_id: int
    gender: str | None
    birth_date: str | None
    height_cm: float | None
    weight_kg: float | None
    diseases: list[str]
    allergies: str | None
    medications: str | None
    emergency_contact: str | None
    health_profile: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


# Health Records
class HealthRecordCreate(BaseModel):
    record_type: RecordType
    value: float
    unit: str
    extra_data: dict[str, Any] = {}
    recorded_at: datetime | None = None


class HealthRecordResponse(BaseModel):
    id: int
    patient_id: int
    record_type: RecordType
    value: float
    unit: str
    extra_data: dict | None
    recorded_at: datetime
    is_abnormal: bool

    model_config = {"from_attributes": True}


class RecordFeedback(BaseModel):
    is_abnormal: bool
    alert_level: str | None
    reference_range: str | None
    message: str
    alert_id: int | None = None


class HealthRecordCreateResult(BaseModel):
    record: HealthRecordResponse
    feedback: RecordFeedback


# Lifestyle
class LifestyleLogCreate(BaseModel):
    log_type: LifestyleType
    content: str
    extra_data: dict[str, Any] = {}
    logged_at: datetime | None = None


class LifestyleLogResponse(BaseModel):
    id: int
    patient_id: int
    log_type: LifestyleType
    content: str
    extra_data: dict | None
    logged_at: datetime

    model_config = {"from_attributes": True}


# Alerts
class AlertResponse(BaseModel):
    id: int
    patient_id: int
    level: AlertLevel
    title: str
    message: str
    source: str
    suggestion: str | None
    is_read: bool
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# Care Plans
class CarePlanResponse(BaseModel):
    id: int
    patient_id: int
    title: str
    diet_plan: dict | None
    exercise_plan: dict | None
    monitoring_plan: dict | None
    medication_notes: str | None
    status: str
    created_by_agent: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Follow-ups
class FollowUpResponse(BaseModel):
    id: int
    patient_id: int
    title: str
    questions: list
    responses: dict | None
    adherence_score: float | None
    status: str
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowUpSubmit(BaseModel):
    responses: dict[str, Any]


# Medical Documents
class MedicalDocumentResponse(BaseModel):
    id: int
    patient_id: int
    filename: str
    doc_type: str
    ocr_text: str | None
    parsed_data: dict | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Agent
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    agent_traces: list[dict[str, Any]] = []
    care_plan: dict | None = None
    alert: dict | None = None


class AgentTraceResponse(BaseModel):
    id: int
    session_id: str
    agent_name: str
    action: str
    input_data: dict | None
    output_data: dict | None
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# 会话（短时记忆）
class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    message_count: int
    last_message_at: datetime


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Dashboard
class DashboardStats(BaseModel):
    today_records: list[HealthRecordResponse]
    recent_alerts: list[AlertResponse]
    active_plan: CarePlanResponse | None
    pending_followups: int
    risk_level: str
    trends: dict[str, list[dict[str, Any]]]


# Knowledge Graph
class KGNode(BaseModel):
    id: str
    label: str
    type: str


class KGEdge(BaseModel):
    source: str
    target: str
    label: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
