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
    Drug,
    DrugInteraction,
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
    "diseases": [        ("diabetes_type2", "2型糖尿病", "胰岛素抵抗或分泌不足导致的慢性代谢性疾病"),
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


DRUG_DATA = [
    {"generic_name": "二甲双胍", "brand_names": ["格华止"], "category": "降糖药", "route": "口服", "dosage_forms": ["片", "缓释片"], "dose_min": 250, "dose_max": 2550, "dose_unit": "mg", "allergy_terms": [], "contraindications": "严重肾功能不全", "notes": "餐中或餐后服用，减少胃肠反应"},
    {"generic_name": "格列美脲", "brand_names": ["亚莫利"], "category": "降糖药", "route": "口服", "dosage_forms": ["片"], "dose_min": 1, "dose_max": 8, "dose_unit": "mg", "allergy_terms": [], "contraindications": "1型糖尿病、酮症酸中毒", "notes": "早餐前服用，注意低血糖"},
    {"generic_name": "阿司匹林", "brand_names": ["拜阿司匹灵"], "category": "抗血小板药", "route": "口服", "dosage_forms": ["肠溶片", "片"], "dose_min": 75, "dose_max": 300, "dose_unit": "mg", "allergy_terms": ["阿司匹林", "水杨酸"], "contraindications": "活动性出血、消化道溃疡", "notes": "餐后服用，注意出血风险"},
    {"generic_name": "氯吡格雷", "brand_names": ["波立维"], "category": "抗血小板药", "route": "口服", "dosage_forms": ["片"], "dose_min": 75, "dose_max": 300, "dose_unit": "mg", "allergy_terms": [], "contraindications": "活动性出血", "notes": "与抗凝药合用需评估出血风险"},
    {"generic_name": "华法林", "brand_names": ["华法林钠片"], "category": "抗凝药", "route": "口服", "dosage_forms": ["片"], "dose_min": 1, "dose_max": 10, "dose_unit": "mg", "allergy_terms": [], "contraindications": "活动性出血", "notes": "需监测 INR"},
    {"generic_name": "硝苯地平", "brand_names": ["拜新同"], "category": "降压药", "route": "口服", "dosage_forms": ["控释片", "片"], "dose_min": 10, "dose_max": 120, "dose_unit": "mg", "allergy_terms": [], "contraindications": "心源性休克", "notes": "避免与西柚同服"},
    {"generic_name": "氨氯地平", "brand_names": ["络活喜"], "category": "降压药", "route": "口服", "dosage_forms": ["片"], "dose_min": 2.5, "dose_max": 10, "dose_unit": "mg", "allergy_terms": [], "contraindications": "严重低血压", "notes": "每日固定时间服用"},
    {"generic_name": "缬沙坦", "brand_names": ["代文"], "category": "降压药", "route": "口服", "dosage_forms": ["胶囊"], "dose_min": 80, "dose_max": 320, "dose_unit": "mg", "allergy_terms": [], "contraindications": "妊娠", "notes": "监测肾功能与血钾"},
    {"generic_name": "美托洛尔", "brand_names": ["倍他乐克"], "category": "降压药", "route": "口服", "dosage_forms": ["片", "缓释片"], "dose_min": 25, "dose_max": 200, "dose_unit": "mg", "allergy_terms": [], "contraindications": "严重心动过缓", "notes": "不可突然停药"},
    {"generic_name": "阿托伐他汀", "brand_names": ["立普妥"], "category": "调脂药", "route": "口服", "dosage_forms": ["片"], "dose_min": 10, "dose_max": 80, "dose_unit": "mg", "allergy_terms": [], "contraindications": "活动性肝病", "notes": "睡前服用，注意肌痛"},
    {"generic_name": "瑞舒伐他汀", "brand_names": ["可定"], "category": "调脂药", "route": "口服", "dosage_forms": ["片"], "dose_min": 5, "dose_max": 40, "dose_unit": "mg", "allergy_terms": [], "contraindications": "活动性肝病", "notes": "注意肌痛与肝酶"},
    {"generic_name": "辛伐他汀", "brand_names": ["舒降之"], "category": "调脂药", "route": "口服", "dosage_forms": ["片"], "dose_min": 10, "dose_max": 80, "dose_unit": "mg", "allergy_terms": [], "contraindications": "活动性肝病", "notes": "避免与大环内酯类合用"},
    {"generic_name": "克拉霉素", "brand_names": ["克拉仙"], "category": "抗生素", "route": "口服", "dosage_forms": ["片", "胶囊"], "dose_min": 250, "dose_max": 1000, "dose_unit": "mg", "allergy_terms": ["大环内酯类", "克拉霉素"], "contraindications": "严重肝功能不全", "notes": "与他汀合用需谨慎"},
    {"generic_name": "红霉素", "brand_names": [], "category": "抗生素", "route": "口服", "dosage_forms": ["片", "胶囊"], "dose_min": 250, "dose_max": 2000, "dose_unit": "mg", "allergy_terms": ["大环内酯类", "红霉素"], "contraindications": "严重肝功能不全", "notes": "可能延长 QT"},
    {"generic_name": "阿莫西林", "brand_names": ["阿莫仙"], "category": "抗生素", "route": "口服", "dosage_forms": ["胶囊", "片"], "dose_min": 250, "dose_max": 1000, "dose_unit": "mg", "allergy_terms": ["青霉素", "青霉素类", "阿莫西林"], "contraindications": "青霉素过敏", "notes": "用前确认过敏史"},
    {"generic_name": "头孢呋辛", "brand_names": ["西力欣"], "category": "抗生素", "route": "口服", "dosage_forms": ["片", "胶囊"], "dose_min": 250, "dose_max": 1000, "dose_unit": "mg", "allergy_terms": ["头孢", "头孢菌素"], "contraindications": "头孢过敏", "notes": "与青霉素可能交叉过敏"},
    {"generic_name": "左氧氟沙星", "brand_names": ["可乐必妥"], "category": "抗生素", "route": "口服", "dosage_forms": ["片", "胶囊"], "dose_min": 250, "dose_max": 750, "dose_unit": "mg", "allergy_terms": ["喹诺酮类", "左氧氟沙星"], "contraindications": "18岁以下、妊娠", "notes": "避免与含铝镁抗酸药同服"},
    {"generic_name": "奥美拉唑", "brand_names": ["洛赛克"], "category": "抑酸药", "route": "口服", "dosage_forms": ["胶囊", "肠溶片"], "dose_min": 20, "dose_max": 40, "dose_unit": "mg", "allergy_terms": [], "contraindications": "严重肝功能不全", "notes": "餐前服用"},
    {"generic_name": "布洛芬", "brand_names": ["芬必得"], "category": "解热镇痛药", "route": "口服", "dosage_forms": ["片", "胶囊"], "dose_min": 200, "dose_max": 800, "dose_unit": "mg", "allergy_terms": ["布洛芬", "非甾体抗炎药"], "contraindications": "消化道溃疡", "notes": "避免与抗凝药合用"},
    {"generic_name": "地高辛", "brand_names": ["地高辛片"], "category": "强心药", "route": "口服", "dosage_forms": ["片"], "dose_min": 0.125, "dose_max": 0.5, "dose_unit": "mg", "allergy_terms": [], "contraindications": "室性心动过速", "notes": "治疗窗窄，需监测血药浓度"},
    {"generic_name": "呋塞米", "brand_names": ["速尿"], "category": "利尿药", "route": "口服", "dosage_forms": ["片"], "dose_min": 20, "dose_max": 80, "dose_unit": "mg", "allergy_terms": ["磺胺", "呋塞米"], "contraindications": "严重低钾", "notes": "注意电解质"},
    {"generic_name": "含碘造影剂", "brand_names": [], "category": "检查用药", "route": "静脉", "dosage_forms": ["注射液"], "dose_min": None, "dose_max": None, "dose_unit": None, "allergy_terms": ["碘", "造影剂"], "contraindications": "碘过敏", "notes": "检查前后需评估肾功能"},
    {"generic_name": "西柚", "brand_names": ["葡萄柚"], "category": "食物", "route": None, "dosage_forms": [], "dose_min": None, "dose_max": None, "dose_unit": None, "allergy_terms": [], "contraindications": None, "notes": "可影响多种药物代谢"},
]

INTERACTION_DATA = [
    {"drug_a": "阿司匹林", "drug_b": "华法林", "severity": "major", "advice": "出血风险显著增加，需医生评估并监测凝血功能"},
    {"drug_a": "氯吡格雷", "drug_b": "华法林", "severity": "major", "advice": "抗血小板与抗凝叠加，出血风险高，需医生评估"},
    {"drug_a": "阿司匹林", "drug_b": "氯吡格雷", "severity": "moderate", "advice": "双联抗血小板增加出血风险，需遵医嘱"},
    {"drug_a": "二甲双胍", "drug_b": "含碘造影剂", "severity": "moderate", "advice": "造影前后需评估肾功能，必要时暂停二甲双胍"},
    {"drug_a": "硝苯地平", "drug_b": "西柚", "severity": "moderate", "advice": "西柚可能升高硝苯地平血药浓度，导致低血压"},
    {"drug_a": "阿托伐他汀", "drug_b": "克拉霉素", "severity": "major", "advice": "可能升高他汀浓度，增加肌痛/肝损伤风险"},
    {"drug_a": "辛伐他汀", "drug_b": "克拉霉素", "severity": "major", "advice": "禁止合用或需大幅减量，警惕横纹肌溶解"},
    {"drug_a": "瑞舒伐他汀", "drug_b": "红霉素", "severity": "moderate", "advice": "可能增加他汀暴露，注意肌痛"},
    {"drug_a": "华法林", "drug_b": "克拉霉素", "severity": "moderate", "advice": "可能增强抗凝作用，需监测 INR"},
    {"drug_a": "地高辛", "drug_b": "呋塞米", "severity": "moderate", "advice": "利尿导致低钾，增加地高辛毒性风险"},
    {"drug_a": "阿司匹林", "drug_b": "布洛芬", "severity": "moderate", "advice": "布洛芬可能减弱阿司匹林抗血小板作用并增加胃肠出血"},
    {"drug_a": "氨氯地平", "drug_b": "辛伐他汀", "severity": "moderate", "advice": "可能升高辛伐他汀浓度，建议限制剂量"},
    {"drug_a": "左氧氟沙星", "drug_b": "氨氯地平", "severity": "minor", "advice": "可能轻度延长 QT，注意心悸"},
    {"drug_a": "奥美拉唑", "drug_b": "氯吡格雷", "severity": "moderate", "advice": "可能降低氯吡格雷活性，需医生评估"},
]


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

        # Drug library & interactions（按名称幂等）
        existing_drugs = {
            d.generic_name for d in (await db.execute(select(Drug))).scalars().all()
        }
        for item in DRUG_DATA:
            if item["generic_name"] not in existing_drugs:
                db.add(Drug(**item))

        existing_pairs = {
            (i.drug_a, i.drug_b)
            for i in (await db.execute(select(DrugInteraction))).scalars().all()
        }
        for item in INTERACTION_DATA:
            pair = (item["drug_a"], item["drug_b"])
            if pair not in existing_pairs and (pair[1], pair[0]) not in existing_pairs:
                db.add(DrugInteraction(**item))
                existing_pairs.add(pair)

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
