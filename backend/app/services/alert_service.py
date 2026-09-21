from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertLevel, AlertThreshold, HealthRecord, Patient
from app.services.ml_service import MLRiskService
from app.services.redis_client import redis_client


DEFAULT_THRESHOLDS = [
    {"disease": "diabetes_type2", "record_type": "blood_glucose", "yellow_max": 7.0, "orange_max": 11.1, "red_max": 16.7, "unit": "mmol/L"},
    {"disease": "diabetes_type2", "record_type": "blood_glucose", "metric_key": "fasting", "yellow_max": 7.0, "orange_max": 10.0, "red_max": 13.9, "unit": "mmol/L"},
    {"disease": "diabetes_type2", "record_type": "blood_glucose", "metric_key": "postprandial", "yellow_max": 10.0, "orange_max": 13.9, "red_max": 16.7, "unit": "mmol/L"},
    {"disease": "diabetes_type2", "record_type": "blood_glucose", "metric_key": "random", "yellow_max": 11.1, "orange_max": 13.9, "red_max": 16.7, "unit": "mmol/L"},
    {"disease": "diabetes_type2", "record_type": "blood_glucose", "metric_key": "bedtime", "yellow_max": 8.0, "orange_max": 10.0, "red_max": 13.9, "unit": "mmol/L"},
    {"disease": "hypertension", "record_type": "blood_pressure", "metric_key": "systolic", "yellow_max": 140, "orange_max": 160, "red_max": 180, "unit": "mmHg"},
    {"disease": "hypertension", "record_type": "blood_pressure", "metric_key": "diastolic", "yellow_max": 90, "orange_max": 100, "red_max": 110, "unit": "mmHg"},
    {"disease": "hyperlipidemia", "record_type": "blood_lipid", "metric_key": "ldl", "yellow_max": 3.4, "orange_max": 4.1, "red_max": 4.9, "unit": "mmol/L"},
    {"disease": "copd", "record_type": "spo2", "yellow_min": 94, "orange_min": 90, "red_min": 85, "unit": "%"},
]

REFERENCE_RANGES: dict[tuple[str, str], str] = {
    ("blood_glucose", "value"): "4.4-7.0 mmol/L",
    ("blood_glucose", "fasting"): "4.4-7.0 mmol/L",
    ("blood_glucose", "postprandial"): "<10.0 mmol/L",
    ("blood_glucose", "random"): "<11.1 mmol/L",
    ("blood_glucose", "bedtime"): "4.4-8.0 mmol/L",
    ("blood_pressure", "systolic"): "90-140 mmHg",
    ("blood_pressure", "diastolic"): "60-90 mmHg",
    ("weight", "value"): "因个人而异",
    ("blood_lipid", "value"): "LDL-C <3.4 mmol/L",
    ("spo2", "value"): "≥94%",
}

RECORD_TYPE_LABELS = {
    "blood_glucose": "血糖",
    "blood_pressure": "血压",
    "weight": "体重",
    "blood_lipid": "血脂",
    "spo2": "血氧",
    "heart_rate": "心率",
}

GLUCOSE_CONTEXT_LABELS = {
    "fasting": "空腹",
    "postprandial": "餐后2h",
    "random": "随机",
    "bedtime": "睡前",
}


def get_reference_range(record_type: str, metric_key: str = "value") -> str | None:
    return REFERENCE_RANGES.get((record_type, metric_key)) or REFERENCE_RANGES.get((record_type, "value"))


def get_metric_key(record_type: str, extra_data: dict | None) -> str:
    if record_type == "blood_pressure":
        return "systolic"
    if extra_data and "type" in extra_data:
        return extra_data.get("type", "value")
    return "value"


def build_feedback_message(
    record_type: str, level: AlertLevel | None, extra_data: dict | None, is_abnormal: bool
) -> str:
    label = RECORD_TYPE_LABELS.get(record_type, record_type)
    if record_type == "blood_glucose" and extra_data and extra_data.get("type"):
        ctx = GLUCOSE_CONTEXT_LABELS.get(extra_data["type"], "")
        if ctx:
            label = f"{ctx}{label}"
    if not is_abnormal and not level:
        return f"{label}在正常范围内，请继续保持。"
    if level == AlertLevel.red:
        return f"{label}严重异常，请立即就医。"
    if level == AlertLevel.orange:
        return f"{label}异常，建议尽快联系医生。"
    if level == AlertLevel.yellow:
        return f"{label}偏高，请关注并继续监测。"
    return f"{label}已记录。"


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ml = MLRiskService(db)

    async def ensure_thresholds(self):
        result = await self.db.execute(select(AlertThreshold).limit(1))
        if result.scalar_one_or_none():
            return
        for t in DEFAULT_THRESHOLDS:
            self.db.add(AlertThreshold(**t))
        await self.db.flush()

    async def check_threshold(
        self, diseases: list[str], record_type: str, value: float, extra_data: dict | None
    ) -> tuple[bool, AlertLevel | None]:
        await self.ensure_thresholds()
        metric_key = "value"
        check_value = value
        if record_type == "blood_pressure" and extra_data:
            metric_key = "systolic"
            check_value = extra_data.get("systolic", value)
        elif extra_data and "type" in extra_data:
            metric_key = extra_data.get("type", "value")

        result = await self.db.execute(
            select(AlertThreshold).where(
                AlertThreshold.record_type == record_type,
                AlertThreshold.disease.in_(diseases) if diseases else True,
            )
        )
        thresholds = result.scalars().all()
        if not thresholds:
            thresholds_data = [t for t in DEFAULT_THRESHOLDS if t["record_type"] == record_type]
        else:
            thresholds_data = thresholds

        has_typed_context = bool(extra_data and "type" in extra_data)
        level = None
        for th in thresholds_data:
            td = th if isinstance(th, AlertThreshold) else th
            mk = td.metric_key if hasattr(td, "metric_key") else td.get("metric_key", "value")
            if has_typed_context:
                if mk != metric_key:
                    continue
            elif mk != metric_key and mk != "value":
                continue
            cv = check_value
            red_max = getattr(td, "red_max", None) or (td.get("red_max") if isinstance(td, dict) else None)
            orange_max = getattr(td, "orange_max", None) or (td.get("orange_max") if isinstance(td, dict) else None)
            yellow_max = getattr(td, "yellow_max", None) or (td.get("yellow_max") if isinstance(td, dict) else None)
            red_min = getattr(td, "red_min", None) or (td.get("red_min") if isinstance(td, dict) else None)
            orange_min = getattr(td, "orange_min", None) or (td.get("orange_min") if isinstance(td, dict) else None)
            yellow_min = getattr(td, "yellow_min", None) or (td.get("yellow_min") if isinstance(td, dict) else None)

            if red_max and cv >= red_max:
                level = AlertLevel.red
            elif orange_max and cv >= orange_max:
                level = AlertLevel.orange
            elif yellow_max and cv >= yellow_max:
                level = AlertLevel.yellow
            if red_min and cv <= red_min:
                level = AlertLevel.red
            elif orange_min and cv <= orange_min:
                level = AlertLevel.orange if not level else level
            elif yellow_min and cv <= yellow_min:
                level = AlertLevel.yellow if not level else level

        return (level is not None and level != AlertLevel.green, level)

    async def evaluate_record(self, patient: Patient, record: HealthRecord) -> Alert | None:
        is_abnormal, level = await self.check_threshold(
            patient.diseases or [],
            record.record_type.value,
            record.value,
            record.extra_data,
        )
        ml_score = await self.ml.compute_risk_score(patient.id)
        if ml_score > 0.7 and (not level or level == AlertLevel.yellow):
            level = AlertLevel.orange

        if not is_abnormal and not level:
            return None

        level = level or AlertLevel.yellow
        titles = {
            AlertLevel.yellow: "指标偏高，请关注",
            AlertLevel.orange: "指标异常，建议尽快处理",
            AlertLevel.red: "严重异常，请立即就医",
        }
        suggestions = {
            AlertLevel.yellow: "请继续监测，注意饮食和作息，必要时咨询医生。",
            AlertLevel.orange: "建议尽快联系医生，调整用药或治疗方案。",
            AlertLevel.red: "请立即就医或拨打急救电话，本建议仅供参考。",
        }
        alert = Alert(
            patient_id=patient.id,
            level=level,
            title=titles.get(level, "健康预警"),
            message=f"您的{record.record_type.value}指标为 {record.value}{record.unit}，超出正常范围。",
            source="warning_agent",
            suggestion=suggestions.get(level),
            extra_data={"record_id": record.id, "ml_score": ml_score},
        )
        self.db.add(alert)
        await self.db.flush()

        alert_data = {
            "id": alert.id,
            "level": alert.level.value,
            "title": alert.title,
            "message": alert.message,
            "suggestion": alert.suggestion,
        }
        await redis_client.push_alert_stream(alert_data)
        await redis_client.publish_alert(patient.id, alert_data)
        return alert

    async def list_alerts(self, patient_id: int, unresolved_only: bool = False) -> list[Alert]:
        query = select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc())
        if unresolved_only:
            query = query.where(Alert.is_resolved == False)
        result = await self.db.execute(query)
        return list(result.scalars().all())
