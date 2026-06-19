"""Seed database with knowledge graph and demo data."""
import sys
from pathlib import Path

# Allow `python scripts/seed.py` from project root or Docker /app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from sqlalchemy import select

from app.auth import hash_password
from app.database import AsyncSessionLocal, Base, engine
from app.models import (
    AlertThreshold,
    DietRecommendation,
    Disease,
    DiseaseSymptom,
    FollowUp,
    HealthRecord,
    Patient,
    RecordType,
    Symptom,
    Treatment,
    User,
    UserRole,
)
from app.services.alert_service import DEFAULT_THRESHOLDS, AlertService
from app.services.rag_service import RAGService

KG_DATA = {
    "diseases": [
        ("diabetes_type2", "2型糖尿病", "胰岛素抵抗或分泌不足导致的慢性代谢性疾病"),
        ("hypertension", "高血压", "动脉血压持续升高的慢性疾病"),
        ("hyperlipidemia", "高血脂", "血脂水平异常升高的代谢性疾病"),
        ("copd", "慢阻肺", "慢性阻塞性肺疾病，气流受限为特征"),
    ],
    "symptoms": [
        ("多饮多尿", "血糖升高导致的多饮、多尿、多食"),
        ("头晕头痛", "血压波动或脑供血不足引起"),
        ("胸闷气短", "心肺功能受损的表现"),
        ("乏力", "代谢异常或缺氧导致"),
    ],
    "disease_symptoms": [(1, 1), (1, 4), (2, 2), (2, 4), (3, 4), (4, 3), (4, 4)],
    "treatments": [
        (1, "二甲双胍", "一线降糖药物，改善胰岛素敏感性", "medication"),
        (1, "饮食控制", "低糖低脂饮食，控制总热量", "lifestyle"),
        (2, "ACEI/ARB类药物", "降压并保护靶器官", "medication"),
        (2, "限盐", "每日食盐摄入<5g", "lifestyle"),
        (3, "他汀类药物", "降低胆固醇和LDL-C", "medication"),
        (4, "支气管扩张剂", "缓解气流受限", "medication"),
        (4, "肺康复训练", "改善呼吸功能", "rehabilitation"),
    ],
    "diets": [
        (1, "蔬菜", "每日摄入500g以上新鲜蔬菜", False),
        (1, "精制碳水", "减少白米饭、白面包等精制碳水", True),
        (2, "高盐食品", "避免腌制品、咸菜等高盐食物", True),
        (2, "钾丰富食物", "适量香蕉、菠菜等富钾食物", False),
        (3, "饱和脂肪", "减少动物油脂、油炸食品", True),
        (4, "清淡饮食", "易消化、营养均衡", False),
    ],
}


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Demo user
        result = await db.execute(select(User).where(User.email == "demo@nurse.com"))
        if not result.scalar_one_or_none():
            user = User(
                email="demo@nurse.com",
                hashed_password=hash_password("demo123"),
                full_name="演示患者",
                role=UserRole.patient,
                agreed_disclaimer=True,
            )
            db.add(user)
            await db.flush()
            patient = Patient(
                user_id=user.id,
                gender="男",
                birth_date="1965-03-15",
                height_cm=170,
                weight_kg=75,
                diseases=["diabetes_type2", "hypertension"],
                allergies="青霉素",
                medications="二甲双胍 0.5g bid, 氨氯地平 5mg qd",
                emergency_contact="13800138000",
            )
            db.add(patient)
            await db.flush()

            from datetime import datetime, timedelta, timezone
            import random
            base = datetime.now(timezone.utc)
            for i in range(7):
                day = base - timedelta(days=6 - i)
                db.add(HealthRecord(
                    patient_id=patient.id,
                    record_type=RecordType.blood_glucose,
                    value=round(random.uniform(5.5, 8.5), 1),
                    unit="mmol/L",
                    recorded_at=day,
                    is_abnormal=random.random() > 0.7,
                ))
                db.add(HealthRecord(
                    patient_id=patient.id,
                    record_type=RecordType.blood_pressure,
                    value=130,
                    unit="mmHg",
                    extra_data={"systolic": random.randint(125, 155), "diastolic": random.randint(75, 95)},
                    recorded_at=day,
                    is_abnormal=random.random() > 0.8,
                ))

            db.add(FollowUp(
                patient_id=patient.id,
                title="本周慢病管理随访",
                questions=[
                    {"id": "q1", "text": "本周是否按时服药？", "type": "boolean"},
                    {"id": "q2", "text": "监测指标频率？", "type": "choice", "options": ["每天", "每周", "很少"]},
                    {"id": "q3", "text": "方案执行评分(1-5)", "type": "scale", "min": 1, "max": 5},
                ],
                status="pending",
            ))

        # Knowledge Graph
        if not (await db.execute(select(Disease).limit(1))).scalar_one_or_none():
            disease_map = {}
            for code, name, desc in KG_DATA["diseases"]:
                d = Disease(code=code, name=name, description=desc)
                db.add(d)
                await db.flush()
                disease_map[code] = d.id

            symptom_map = {}
            for name, desc in KG_DATA["symptoms"]:
                s = Symptom(name=name, description=desc)
                db.add(s)
                await db.flush()
                symptom_map[name] = s.id

            symptoms_list = list(symptom_map.values())
            for d_id, s_idx in KG_DATA["disease_symptoms"]:
                db.add(DiseaseSymptom(disease_id=d_id, symptom_id=symptoms_list[s_idx - 1]))

            for d_id, name, desc, ttype in KG_DATA["treatments"]:
                db.add(Treatment(disease_id=d_id, name=name, description=desc, treatment_type=ttype))

            for d_id, category, rec, avoid in KG_DATA["diets"]:
                db.add(DietRecommendation(disease_id=d_id, food_category=category, recommendation=rec, avoid=avoid))

        # Thresholds
        alert_svc = AlertService(db)
        await alert_svc.ensure_thresholds()

        # RAG knowledge
        rag = RAGService(db)
        await rag.seed_knowledge()

        await db.commit()
        print("Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
