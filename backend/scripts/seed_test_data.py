"""测试数据种子脚本（可重复执行、结果可断言）。

目标
----
为「贴心小护士」生成一套隔离的测试数据，覆盖：
- 单病 / 多病共存患者；
- yellow / orange / red 三档异常与阈值边界值；
- 7 天 / 30 天趋势；
- 空数据患者；
- 医疗文档（化验单 / 处方 / 出院小结 / 门诊病历）；
- 用药 qd / bid / tid / qid / q8h / qn / prn 各频次；
- 过敏冲突、药物相互作用、剂量异常、重复用药。

隔离与幂等
----------
- 测试账号统一为 ``test.<slug>@nurse.com``，与演示账号 ``demo@nurse.com`` 完全隔离；
- 每次执行先删除本脚本拥有的测试账号及其患者数据，再重新生成；
- 不修改业务代码，不直接手写 SQL 插业务表，全部通过模型/服务层写入；
- 全局参考数据（Drug / DrugInteraction / AlertThreshold）按名称幂等补齐，不覆盖已有值。

确定性说明
----------
- 所有健康指标数值写死，不使用 random；
- 预警等级由 ``AlertService.check_threshold``（规则引擎）计算后直接落 Alert，
  不使用 ``evaluate_record`` 的 ML 提级（避免 IsolationForest 对断言的影响）；
- 文档分类使用 ``document_parser._classify_keywords``（关键词兜底，确定性），
  不调用 LLM；配置了 ``LLM_API_KEY`` 时线上 ``classify_document`` 可能走 LLM，
  以线上结果为准；
- 时间戳以执行时刻为基准做相对偏移，保证趋势窗口始终有数据；数值与等级不受影响。

运行
----
    cd backend
    python scripts/seed_test_data.py            # 本地库
    docker compose exec backend python scripts/seed_test_data.py

若 DATABASE_URL 指向非本地/容器内主机，脚本默认拒绝执行；
确认目标不是生产库时可追加 ``--force``。

测试账号密码统一为 ``test123456``。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select, text
from sqlalchemy.engine.url import make_url

from app.auth import hash_password
from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.graph.orchestrator import DOCUMENT_MARKERS
from app.models import (
    AgentTrace,
    Alert,
    AlertLevel,
    CarePlan,
    ChatMessage,
    Drug,
    DrugInteraction,
    FollowUp,
    HealthRecord,
    LifestyleLog,
    LifestyleType,
    MedicalDocument,
    MedicationLog,
    MedicationReminder,
    Patient,
    RecordType,
    User,
    UserRole,
)
from app.schemas import HealthRecordCreate, MedicationReminderCreate
from app.services.alert_service import AlertService
from app.services.document_parser import _classify_keywords, _extract_lab_report_regex
from app.services.drug_service import DrugSafetyService
from app.services.health_service import HealthService
from app.services.reminder_service import ReminderService, expand_times

TEST_PASSWORD = "test123456"
SAMPLES_DIR = BACKEND_ROOT / "knowledge" / "samples"

# 本脚本创建/清理的账号（slug 会拼成 test.<slug>@nurse.com）
TEST_SLUGS = [
    "single.diabetes",
    "single.hypertension",
    "bp.diastolic",
    "single.hyperlipidemia",
    "lipid.nocontext",
    "single.copd",
    "multi",
    "trend7",
    "trend30",
    "empty",
    "med.freq",
    "med.safety",
    "med.safety2",
    "documents",
]

ALERT_TITLES = {
    AlertLevel.yellow: "指标偏高，请关注",
    AlertLevel.orange: "指标异常，建议尽快处理",
    AlertLevel.red: "严重异常，请立即就医",
}
ALERT_SUGGESTIONS = {
    AlertLevel.yellow: "请继续监测，注意饮食和作息，必要时咨询医生。",
    AlertLevel.orange: "建议尽快联系医生，调整用药或治疗方案。",
    AlertLevel.red: "请立即就医或拨打急救电话，本建议仅供参考。",
}

# 用药安全用例需要的药品与相互作用（从 seed.py 的权威数据中筛选，避免重复维护）
NEEDED_DRUGS = {
    "阿莫西林",
    "阿司匹林",
    "华法林",
    "辛伐他汀",
    "克拉霉素",
    "瑞舒伐他汀",
    "红霉素",
    "二甲双胍",
    "氨氯地平",
    "硝苯地平",
    "缬沙坦",
    "奥美拉唑",
    "阿托伐他汀",
}
NEEDED_INTERACTIONS = {
    ("阿司匹林", "华法林"),
    ("辛伐他汀", "克拉霉素"),
    ("瑞舒伐他汀", "红霉素"),
}


# ---------------------------------------------------------------------------
# 文档 parsed_data（与 document_parser 的提示词 / 前端 DocumentsPage 形状一致）
# ---------------------------------------------------------------------------

LAB_PARSED = {
    "doc_type": "lab_report",
    "confidence": 0.9,
    "exam_date": "2026-10-08",
    "metrics": [
        {"name": "空腹血糖", "record_type": "blood_glucose", "value": 8.0, "unit": "mmol/L",
         "context": "fasting", "systolic": None, "diastolic": None,
         "reference": "3.9-6.1", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "餐后2小时血糖", "record_type": "blood_glucose", "value": 14.5, "unit": "mmol/L",
         "context": "postprandial", "systolic": None, "diastolic": None,
         "reference": "<7.8", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "血压", "record_type": "blood_pressure", "value": 165.0, "unit": "mmHg",
         "context": None, "systolic": 165.0, "diastolic": 100.0,
         "reference": "90-140/60-90", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "心率", "record_type": "heart_rate", "value": 78.0, "unit": "次/分",
         "context": None, "systolic": None, "diastolic": None,
         "reference": "60-100", "abnormal_flag": None, "confidence": 0.95},
        {"name": "血氧", "record_type": "spo2", "value": 88.0, "unit": "%",
         "context": None, "systolic": None, "diastolic": None,
         "reference": "95-100", "abnormal_flag": "L", "confidence": 0.95},
        {"name": "总胆固醇", "record_type": "blood_lipid", "value": 5.8, "unit": "mmol/L",
         "context": "tc", "systolic": None, "diastolic": None,
         "reference": "<5.2", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "甘油三酯", "record_type": "blood_lipid", "value": 2.1, "unit": "mmol/L",
         "context": "tg", "systolic": None, "diastolic": None,
         "reference": "<1.7", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "低密度脂蛋白", "record_type": "blood_lipid", "value": 4.2, "unit": "mmol/L",
         "context": "ldl", "systolic": None, "diastolic": None,
         "reference": "<3.4", "abnormal_flag": "H", "confidence": 0.95},
        {"name": "高密度脂蛋白", "record_type": "blood_lipid", "value": 1.0, "unit": "mmol/L",
         "context": "hdl", "systolic": None, "diastolic": None,
         "reference": ">1.0", "abnormal_flag": None, "confidence": 0.95},
        {"name": "体重", "record_type": "weight", "value": 70.0, "unit": "kg",
         "context": None, "systolic": None, "diastolic": None,
         "reference": "因个人而异", "abnormal_flag": None, "confidence": 0.95},
    ],
}

PRESCRIPTION_PARSED = {
    "doc_type": "prescription",
    "confidence": 0.9,
    "hospital": "XX市人民医院",
    "department": "内分泌科",
    "doctor": "李医生",
    "issue_date": "2026-10-08",
    "medications": [
        {"name": "阿莫西林胶囊", "generic_name": "阿莫西林", "spec": "500mg", "dose": 500,
         "dose_unit": "mg", "frequency": "bid", "route": "口服", "timing_note": "饭后",
         "duration_days": 7, "notes": None, "confidence": 0.95},
        {"name": "辛伐他汀片", "generic_name": "辛伐他汀", "spec": "20mg", "dose": 20,
         "dose_unit": "mg", "frequency": "qn", "route": "口服", "timing_note": "睡前",
         "duration_days": 30, "notes": None, "confidence": 0.95},
        {"name": "克拉霉素片", "generic_name": "克拉霉素", "spec": "250mg", "dose": 250,
         "dose_unit": "mg", "frequency": "bid", "route": "口服", "timing_note": "饭后",
         "duration_days": 7, "notes": None, "confidence": 0.95},
        {"name": "二甲双胍片", "generic_name": "二甲双胍", "spec": "500mg", "dose": 500,
         "dose_unit": "mg", "frequency": "bid", "route": "口服", "timing_note": "饭后",
         "duration_days": 30, "notes": None, "confidence": 0.95},
    ],
}

DISCHARGE_PARSED = {
    "doc_type": "discharge_summary",
    "confidence": 0.9,
    "diagnoses": ["2型糖尿病", "高血压3级", "高脂血症"],
    "chief_complaint": "口干、多饮、多尿伴头晕1月余，加重1周",
    "key_abnormal": [
        {"item": "空腹血糖", "value": "13.2", "unit": "mmol/L", "ref": "3.9-6.1", "flag": "high"},
        {"item": "糖化血红蛋白", "value": "9.8", "unit": "%", "ref": "<7.0", "flag": "high"},
        {"item": "低密度脂蛋白", "value": "4.3", "unit": "mmol/L", "ref": "<3.4", "flag": "high"},
        {"item": "血压", "value": "168/102", "unit": "mmHg", "ref": "90-140/60-90", "flag": "high"},
    ],
    "medications": [
        {"name": "二甲双胍片", "dose": "500mg", "frequency": "bid", "note": None},
        {"name": "阿托伐他汀钙片", "dose": "20mg", "frequency": "qn", "note": None},
    ],
    "doctor_orders": [
        "低盐低脂糖尿病饮食",
        "每日监测血糖血压",
        "出院1周后内分泌科复诊",
        "按时服药，如有胸痛、意识不清立即就医",
    ],
    "risk_flags": ["血糖控制不佳，糖化血红蛋白9.8%", "高血压3级，需警惕心脑血管事件"],
    "allergies": None,
    "past_history": "高血压病史10年，最高血压180/110mmHg；否认药物过敏史",
    "summary_text": (
        "您因口干多饮多尿伴头晕住院，诊断为2型糖尿病、高血压3级和高脂血症，"
        "血糖、糖化血红蛋白、低密度脂蛋白和血压均偏高。出院后请低盐低脂糖尿病饮食，"
        "每天监测血糖血压，一周后到内分泌科复诊，并按医嘱服用二甲双胍和阿托伐他汀。"
    ),
}

OUTPATIENT_PARSED = {
    "doc_type": "outpatient_record",
    "confidence": 0.9,
    "diagnoses": ["2型糖尿病", "高血压2级"],
    "chief_complaint": "反复头晕3天，伴乏力",
    "key_abnormal": [
        {"item": "血压", "value": "152/96", "unit": "mmHg", "ref": "90-140/60-90", "flag": "high"},
        {"item": "空腹血糖", "value": "7.8", "unit": "mmol/L", "ref": "3.9-6.1", "flag": "high"},
        {"item": "糖化血红蛋白", "value": "7.5", "unit": "%", "ref": "<7.0", "flag": "high"},
    ],
    "medications": [
        {"name": "二甲双胍片", "dose": "500mg", "frequency": "bid", "note": None},
        {"name": "氨氯地平片", "dose": "5mg", "frequency": "qd", "note": None},
    ],
    "doctor_orders": ["调整降压方案", "继续口服降糖药", "低盐低脂饮食", "2周后复诊"],
    "risk_flags": ["血压控制未达标", "血糖轻度升高"],
    "allergies": None,
    "past_history": "2型糖尿病5年，高血压3年；否认药物过敏史",
    "summary_text": (
        "您因反复头晕3天就诊，血压152/96mmHg，空腹血糖7.8mmol/L，糖化血红蛋白7.5%，"
        "诊断为2型糖尿病和高血压2级。建议调整降压方案，继续口服降糖药，"
        "低盐低脂饮食，两周后复诊。"
    ),
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def _check_db_target() -> None:
    """防止误连生产库：非本地/容器内主机默认拒绝，需显式 --force。"""
    url = make_url(settings.database_url)
    host = (url.host or "").lower()
    if host not in {"", "localhost", "127.0.0.1", "postgres"} and "--force" not in sys.argv:
        raise SystemExit(
            f"[seed-test] 拒绝执行：DATABASE_URL host={host!r} 不是本地/容器内地址。"
            "若确认目标不是生产库，请追加 --force。"
        )
    print(f"[seed-test] 目标数据库 host={url.host or '-'} db={url.database or '-'}")


def _load_seed_module():
    """按路径加载 seed.py，复用其中的 DRUG_DATA / INTERACTION_DATA（不执行 seed()）。"""
    seed_path = Path(__file__).resolve().parent / "seed.py"
    spec = importlib.util.spec_from_file_location("_caringnurse_seed", seed_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"[seed-test] 无法加载 {seed_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _cleanup(db) -> None:
    """删除本脚本拥有的测试账号及其患者数据；绝不触碰 demo@nurse.com。"""
    removed = 0
    for slug in TEST_SLUGS:
        email = f"test.{slug}@nurse.com"
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if not user:
            continue
        patient = (
            await db.execute(select(Patient).where(Patient.user_id == user.id))
        ).scalar_one_or_none()
        if patient:
            pid = patient.id
            # 先删子表，再删患者；MedicationLog 在 MedicationReminder 之前
            for model in (
                MedicationLog,
                MedicationReminder,
                Alert,
                HealthRecord,
                LifestyleLog,
                CarePlan,
                FollowUp,
                MedicalDocument,
                AgentTrace,
                ChatMessage,
            ):
                await db.execute(delete(model).where(model.patient_id == pid))
            await db.execute(delete(Patient).where(Patient.id == pid))
        await db.execute(delete(User).where(User.id == user.id))
        removed += 1
    await db.flush()
    print(f"[seed-test] 已清理 {removed} 个既有测试账号（demo@nurse.com 未触碰）")


async def _ensure_drug_library(db) -> None:
    """幂等补齐用药安全用例需要的药品与相互作用（全局参考数据）。"""
    seed_mod = _load_seed_module()
    existing = {
        d.generic_name
        for d in (await db.execute(select(Drug))).scalars().all()
    }
    for item in seed_mod.DRUG_DATA:
        name = item["generic_name"]
        if name not in NEEDED_DRUGS or name in existing:
            continue
        db.add(Drug(**item))
        existing.add(name)

    missing = NEEDED_DRUGS - existing
    if missing:
        raise RuntimeError(f"[seed-test] seed.py 的 DRUG_DATA 缺少药品：{sorted(missing)}")

    existing_pairs = {
        (i.drug_a, i.drug_b)
        for i in (await db.execute(select(DrugInteraction))).scalars().all()
    }
    for item in seed_mod.INTERACTION_DATA:
        pair = (item["drug_a"], item["drug_b"])
        if pair not in NEEDED_INTERACTIONS:
            continue
        if pair in existing_pairs or (pair[1], pair[0]) in existing_pairs:
            continue
        db.add(DrugInteraction(**item))
        existing_pairs.add(pair)

    missing_pairs = {
        p
        for p in NEEDED_INTERACTIONS
        if p not in existing_pairs and (p[1], p[0]) not in existing_pairs
    }
    if missing_pairs:
        raise RuntimeError(f"[seed-test] seed.py 的 INTERACTION_DATA 缺少相互作用：{sorted(missing_pairs)}")
    await db.flush()


async def _create_patient(
    db,
    slug: str,
    full_name: str,
    diseases: list[str],
    *,
    allergies: str | None = None,
    medications: str | None = None,
    gender: str = "男",
    birth_date: str = "1960-01-01",
    height_cm: float | None = 170.0,
    weight_kg: float | None = 70.0,
) -> Patient:
    email = f"test.{slug}@nurse.com"
    user = User(
        email=email,
        hashed_password=hash_password(TEST_PASSWORD),
        full_name=full_name,
        role=UserRole.patient,
        is_active=True,
        agreed_disclaimer=True,
    )
    db.add(user)
    await db.flush()

    patient = Patient(
        user_id=user.id,
        gender=gender,
        birth_date=birth_date,
        height_cm=height_cm,
        weight_kg=weight_kg,
        diseases=list(diseases),
        allergies=allergies,
        medications=medications,
        emergency_contact="13800000000",
        health_profile={"source": "seed_test", "slug": slug},
    )
    db.add(patient)
    await db.flush()
    return patient


async def _add_record(
    db,
    patient: Patient,
    record_type: RecordType,
    value: float,
    unit: str,
    extra_data: dict | None,
    recorded_at: datetime,
    *,
    create_alert: bool = True,
    expect_level: str | None = None,
) -> HealthRecord:
    """通过 HealthService 写记录，并用规则引擎断言等级。

    - is_abnormal 由 HealthService.create_record 内部调用 check_threshold 得出；
    - 预警等级由 check_threshold 再算一次，直接落 Alert（不经 ML 提级）；
    - expect_level=None 表示预期正常（无预警）。
    """
    record = await HealthService(db).create_record(
        patient,
        HealthRecordCreate(
            record_type=record_type,
            value=float(value),
            unit=unit,
            extra_data=extra_data or {},
            recorded_at=recorded_at,
        ),
    )
    _, level = await AlertService(db).check_threshold(
        patient.diseases or [],
        record.record_type.value,
        record.value,
        record.extra_data,
    )
    actual_level = level.value if level else None
    if record.is_abnormal != (actual_level is not None):
        raise AssertionError(
            f"{patient.user_id} {record.record_type.value}={record.value} "
            f"is_abnormal={record.is_abnormal} 与规则等级 {actual_level} 不一致"
        )
    if actual_level != expect_level:
        raise AssertionError(
            f"{patient.user_id} {record.record_type.value}={record.value} "
            f"预期等级 {expect_level!r}，实际 {actual_level!r}"
        )

    if create_alert and level is not None:
        db.add(
            Alert(
                patient_id=patient.id,
                level=level,
                title=ALERT_TITLES[level],
                message=(
                    f"您的{record.record_type.value}指标为 "
                    f"{record.value}{record.unit}，超出正常范围。"
                ),
                source="warning_agent",
                suggestion=ALERT_SUGGESTIONS[level],
                is_read=False,
                is_resolved=False,
                # 说明：本脚本直接落规则等级，ml_score 固定 0 表示未套用 ML 提级
                extra_data={"record_id": record.id, "fixture": True, "ml_score": 0.0},
            )
        )
        await db.flush()
    return record


async def _add_reminder(
    db,
    patient: Patient,
    name: str,
    dose: float | None,
    dose_unit: str | None,
    frequency: str,
    *,
    timing_note: str | None = None,
    route: str = "口服",
    notes: str | None = None,
    expect_times: list[str] | None = None,
) -> MedicationReminder:
    reminder = await ReminderService(db).create(
        patient.id,
        MedicationReminderCreate(
            medication_name=name,
            dose=dose,
            dose_unit=dose_unit,
            frequency=frequency,
            timing_note=timing_note,
            route=route,
            notes=notes,
        ),
    )
    expected = expect_times if expect_times is not None else expand_times(frequency, timing_note)
    if list(reminder.times_of_day or []) != list(expected):
        raise AssertionError(
            f"{name} frequency={frequency} timing_note={timing_note!r} "
            f"预期 times_of_day={expected}，实际 {reminder.times_of_day}"
        )
    return reminder


async def _add_checkin(
    db, reminder: MedicationReminder, on_date: date, slot: str, status: str
) -> None:
    db.add(
        MedicationLog(
            patient_id=reminder.patient_id,
            reminder_id=reminder.id,
            medication_name=reminder.medication_name,
            local_date=on_date,
            time_of_day=slot,
            status=status,
            reason=None,
        )
    )
    await db.flush()


async def _add_document(
    db,
    patient: Patient,
    filename: str,
    expected_type: str,
    parsed_data: dict,
) -> tuple[MedicalDocument, str]:
    path = SAMPLES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"[seed-test] 缺少样本文件：{path}")
    text = path.read_text(encoding="utf-8")

    if len(text) < 80:
        raise AssertionError(f"{filename} 长度 {len(text)} < 80，不满足病历识别长度门槛")
    markers = sum(1 for marker in DOCUMENT_MARKERS if marker in text)
    if markers < 2:
        raise AssertionError(f"{filename} 仅命中 {markers} 个病历结构标记词（要求 ≥2）")

    keyword_type = _classify_keywords(text)
    if keyword_type != expected_type:
        raise AssertionError(
            f"{filename} 关键词分类预期 {expected_type}，实际 {keyword_type}"
        )

    doc = MedicalDocument(
        patient_id=patient.id,
        filename=filename,
        file_path=f"seed-test/{filename}",
        doc_type=expected_type,
        confidence=parsed_data.get("confidence"),
        ocr_text=text,
        parsed_data=parsed_data,
        # 用 uploaded（10 字符）而非 awaiting_confirmation（21 字符），
        # 后者超过模型 String(20) 上限；两者都可被 /documents/{id}/confirm 确认。
        status="uploaded",
    )
    db.add(doc)
    await db.flush()
    return doc, text


def _assert_lab_regex_matches(text: str, parsed: dict) -> None:
    """化验单样本必须能被正则兜底解析出与 parsed_data 一致的指标。"""
    result = _extract_lab_report_regex(text)
    actual = {
        (m["record_type"], round(float(m["value"]), 2), m.get("context"))
        for m in result.get("metrics", [])
    }
    expected = set()
    for metric in parsed.get("metrics", []):
        if metric["record_type"] == "blood_pressure":
            expected.add(("blood_pressure", round(float(metric["systolic"]), 2), None))
        else:
            expected.add(
                (metric["record_type"], round(float(metric["value"]), 2), metric.get("context"))
            )
    missing = expected - actual
    if missing:
        raise AssertionError(f"化验单正则抽取缺少指标：{sorted(missing)}")
    if result.get("exam_date") != parsed.get("exam_date"):
        raise AssertionError(
            f"化验单检测日期预期 {parsed.get('exam_date')}，实际 {result.get('exam_date')}"
        )


async def _assert_counts(
    db,
    patient: Patient,
    *,
    label: str,
    records: int,
    alerts: dict[str, int],
    abnormal: int | None = None,
) -> None:
    recs = (
        await db.execute(select(HealthRecord).where(HealthRecord.patient_id == patient.id))
    ).scalars().all()
    als = (
        await db.execute(select(Alert).where(Alert.patient_id == patient.id))
    ).scalars().all()

    if len(recs) != records:
        raise AssertionError(f"{label} 记录数预期 {records}，实际 {len(recs)}")
    if len(als) != sum(alerts.values()):
        raise AssertionError(f"{label} 预警数预期 {sum(alerts.values())}，实际 {len(als)}")

    got: dict[str, int] = {}
    for alert in als:
        got[alert.level.value] = got.get(alert.level.value, 0) + 1
    if got != alerts:
        raise AssertionError(f"{label} 预警等级分布预期 {alerts}，实际 {got}")

    abnormal_count = sum(1 for r in recs if r.is_abnormal)
    if abnormal is not None and abnormal_count != abnormal:
        raise AssertionError(f"{label} 异常记录数预期 {abnormal}，实际 {abnormal_count}")
    print(
        f"[seed-test] {label}: records={len(recs)} abnormal={abnormal_count} alerts={got}"
    )


async def seed_test_data() -> None:
    _check_db_target()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # 兼容旧库：create_all 不会给已存在的表补列，本地库可能落后于模型。
        has_confidence = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'medical_documents' AND column_name = 'confidence'"
            )
        )
        if has_confidence.scalar_one_or_none() is None:
            await conn.execute(
                text(
                    "ALTER TABLE medical_documents "
                    "ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION"
                )
            )
            print("[seed-test] 已补齐 medical_documents.confidence（本地库落后于模型）")

    async with AsyncSessionLocal() as db:
        try:
            await _cleanup(db)
            await AlertService(db).ensure_thresholds()
            await _ensure_drug_library(db)

            now = datetime.now(timezone.utc)

            # ------------------------------------------------------------------
            # 1) 单病-糖尿病：空腹血糖阈值边界 6.9 / 7.0 / 10.0 / 13.9
            # ------------------------------------------------------------------
            p1 = await _create_patient(
                db, "single.diabetes", "测试-单病糖尿病", ["diabetes_type2"],
                gender="男", birth_date="1958-05-12",
            )
            for value, offset_days, expect in [
                (6.9, 3, None),
                (7.0, 2, "yellow"),
                (10.0, 1, "orange"),
                (13.9, 0, "red"),
            ]:
                await _add_record(
                    db, p1, RecordType.blood_glucose, value, "mmol/L",
                    {"type": "fasting"}, now - timedelta(days=offset_days),
                    expect_level=expect,
                )

            # ------------------------------------------------------------------
            # 2) 单病-高血压：收缩压阈值边界 139 / 140 / 160 / 180
            # ------------------------------------------------------------------
            p2 = await _create_patient(
                db, "single.hypertension", "测试-单病高血压", ["hypertension"],
                gender="男", birth_date="1955-08-20",
            )
            for systolic, diastolic, offset_days, expect in [
                (139, 85, 3, None),
                (140, 90, 2, "yellow"),
                (160, 100, 1, "orange"),
                (180, 110, 0, "red"),
            ]:
                await _add_record(
                    db, p2, RecordType.blood_pressure, float(systolic), "mmHg",
                    {"systolic": float(systolic), "diastolic": float(diastolic)},
                    now - timedelta(days=offset_days),
                    expect_level=expect,
                )

            # 2b) 舒张压单独偏高：当前 check_threshold 只看收缩压，预期不告警
            p2b = await _create_patient(
                db, "bp.diastolic", "测试-舒张压口径", ["hypertension"],
                gender="女", birth_date="1962-03-08",
            )
            await _add_record(
                db, p2b, RecordType.blood_pressure, 130.0, "mmHg",
                {"systolic": 130.0, "diastolic": 105.0},
                now, expect_level=None,
            )

            # ------------------------------------------------------------------
            # 3) 单病-高血脂：LDL-C 阈值边界 3.3 / 3.4 / 4.1 / 4.9
            # ------------------------------------------------------------------
            p3 = await _create_patient(
                db, "single.hyperlipidemia", "测试-单病高血脂", ["hyperlipidemia"],
                gender="男", birth_date="1960-11-02",
            )
            for value, offset_days, expect in [
                (3.3, 3, None),
                (3.4, 2, "yellow"),
                (4.1, 1, "orange"),
                (4.9, 0, "red"),
            ]:
                await _add_record(
                    db, p3, RecordType.blood_lipid, value, "mmol/L",
                    {"type": "ldl"}, now - timedelta(days=offset_days),
                    expect_level=expect,
                )

            # 3b) 血脂未带 context：check_threshold 无法命中 ldl 阈值，预期不告警
            p3b = await _create_patient(
                db, "lipid.nocontext", "测试-血脂无上下文", ["hyperlipidemia"],
                gender="女", birth_date="1968-07-15",
            )
            await _add_record(
                db, p3b, RecordType.blood_lipid, 5.0, "mmol/L",
                None, now, expect_level=None,
            )

            # ------------------------------------------------------------------
            # 4) 单病-慢阻肺：血氧 min 阈值 95 / 94 / 90 / 85
            # ------------------------------------------------------------------
            p4 = await _create_patient(
                db, "single.copd", "测试-单病慢阻肺", ["copd"],
                gender="男", birth_date="1950-02-18",
            )
            for value, offset_days, expect in [
                (95, 3, None),
                (94, 2, "yellow"),
                (90, 1, "orange"),
                (85, 0, "red"),
            ]:
                await _add_record(
                    db, p4, RecordType.spo2, value, "%",
                    None, now - timedelta(days=offset_days),
                    expect_level=expect,
                )

            # ------------------------------------------------------------------
            # 5) 多病共存：四种慢病各一条，覆盖 yellow/orange/red
            # ------------------------------------------------------------------
            p5 = await _create_patient(
                db, "multi", "测试-多病共存",
                ["diabetes_type2", "hypertension", "hyperlipidemia", "copd"],
                allergies="青霉素", gender="男", birth_date="1954-09-30",
                height_cm=172.0, weight_kg=78.0,
            )
            await _add_record(
                db, p5, RecordType.blood_glucose, 8.0, "mmol/L",
                {"type": "fasting"}, now - timedelta(days=3), expect_level="yellow",
            )
            await _add_record(
                db, p5, RecordType.blood_pressure, 165.0, "mmHg",
                {"systolic": 165.0, "diastolic": 95.0},
                now - timedelta(days=2), expect_level="orange",
            )
            await _add_record(
                db, p5, RecordType.blood_lipid, 5.0, "mmol/L",
                {"type": "ldl"}, now - timedelta(days=1), expect_level="red",
            )
            await _add_record(
                db, p5, RecordType.spo2, 88.0, "%",
                None, now, expect_level="orange",
            )

            db.add(
                CarePlan(
                    patient_id=p5.id,
                    title="个性化慢病管理方案（测试）",
                    diet_plan={"items": ["低盐低脂饮食", "每日蔬菜500g", "控制精制碳水"]},
                    exercise_plan={"items": ["每周150分钟中等强度有氧运动", "每日散步30分钟"]},
                    monitoring_plan={"items": ["每日监测血压", "每周监测血糖3次", "每月记录体重"]},
                    medication_notes="请遵医嘱用药，不可自行调整。",
                    status="active",
                    created_by_agent="planner",
                )
            )
            for log_type, content, offset_days in [
                (LifestyleType.diet, "早餐燕麦粥，午餐少盐，晚餐七分饱。", 3),
                (LifestyleType.exercise, "快走30分钟，心率约100次/分。", 2),
                (LifestyleType.sleep, "23:00前入睡，夜间醒1次。", 1),
            ]:
                db.add(
                    LifestyleLog(
                        patient_id=p5.id,
                        log_type=log_type,
                        content=content,
                        extra_data={"fixture": True},
                        logged_at=now - timedelta(days=offset_days),
                    )
                )
            await db.flush()

            # ------------------------------------------------------------------
            # 6) 7 天趋势：14 条记录，其中 4 条异常（均为 yellow）
            # ------------------------------------------------------------------
            p6 = await _create_patient(
                db, "trend7", "测试-7天趋势", ["diabetes_type2", "hypertension"],
                gender="男", birth_date="1965-12-01",
            )
            glucose7 = [6.2, 6.5, 6.8, 7.0, 7.4, 6.6, 6.9]
            glucose7_levels = [None, None, None, "yellow", "yellow", None, None]
            bp7 = [(128, 82), (132, 84), (138, 86), (142, 88), (145, 90), (136, 85), (130, 83)]
            bp7_levels = [None, None, None, "yellow", "yellow", None, None]
            for i in range(7):
                ts = now - timedelta(days=6 - i)
                await _add_record(
                    db, p6, RecordType.blood_glucose, glucose7[i], "mmol/L",
                    {"type": "fasting"}, ts, create_alert=False,
                    expect_level=glucose7_levels[i],
                )
                systolic, diastolic = bp7[i]
                await _add_record(
                    db, p6, RecordType.blood_pressure, float(systolic), "mmHg",
                    {"systolic": float(systolic), "diastolic": float(diastolic)}, ts,
                    create_alert=False, expect_level=bp7_levels[i],
                )

            # ------------------------------------------------------------------
            # 7) 30 天趋势：30 条血糖 + 10 条血压 + 10 条血脂，共 50 条
            # ------------------------------------------------------------------
            p7 = await _create_patient(
                db, "trend30", "测试-30天趋势",
                ["diabetes_type2", "hypertension", "hyperlipidemia"],
                gender="女", birth_date="1957-04-22",
            )
            glucose30 = [
                6.1, 6.3, 6.5, 6.2, 6.7, 6.9, 6.4, 6.0, 6.6, 6.8,
                7.1, 6.5, 6.3, 6.9, 6.2, 6.4, 6.7, 6.1, 6.8, 6.5,
                6.9, 7.3, 6.2, 6.6, 6.4, 6.0, 6.7, 6.3, 6.5, 6.9,
            ]
            for i, value in enumerate(glucose30):
                await _add_record(
                    db, p7, RecordType.blood_glucose, value, "mmol/L",
                    {"type": "fasting"}, now - timedelta(days=29 - i),
                    create_alert=False,
                    expect_level="yellow" if value >= 7.0 else None,
                )

            bp30 = [
                (130, 84), (135, 86), (142, 90), (138, 88), (145, 92),
                (132, 85), (140, 90), (136, 86), (150, 94), (134, 85),
            ]
            for j, (systolic, diastolic) in enumerate(bp30):
                await _add_record(
                    db, p7, RecordType.blood_pressure, float(systolic), "mmHg",
                    {"systolic": float(systolic), "diastolic": float(diastolic)},
                    now - timedelta(days=29 - j * 3), create_alert=False,
                    expect_level="yellow" if systolic >= 140 else None,
                )

            ldl30 = [3.0, 3.2, 3.5, 3.1, 3.6, 3.3, 3.4, 2.9, 3.7, 3.2]
            for j, value in enumerate(ldl30):
                await _add_record(
                    db, p7, RecordType.blood_lipid, value, "mmol/L",
                    {"type": "ldl"}, now - timedelta(days=29 - j * 3),
                    create_alert=False,
                    expect_level="yellow" if value >= 3.4 else None,
                )

            # ------------------------------------------------------------------
            # 8) 空数据：无记录、无预警、无方案、无提醒
            # ------------------------------------------------------------------
            p8 = await _create_patient(
                db, "empty", "测试-空数据", [],
                gender="女", birth_date="1975-06-01",
                height_cm=None, weight_kg=None,
            )

            # ------------------------------------------------------------------
            # 9) 用药频次：qd / bid / tid / qid / q8h / qn / prn + 时点覆盖
            # ------------------------------------------------------------------
            p9 = await _create_patient(
                db, "med.freq", "测试-用药频次",
                ["hypertension", "diabetes_type2"], gender="男", birth_date="1963-10-09",
            )
            r_qd = await _add_reminder(
                db, p9, "氨氯地平片", 5, "mg", "qd", expect_times=["08:00"],
            )
            r_bid = await _add_reminder(
                db, p9, "二甲双胍片", 500, "mg", "bid", expect_times=["08:00", "20:00"],
            )
            await _add_reminder(
                db, p9, "阿司匹林肠溶片", 100, "mg", "tid",
                expect_times=["08:00", "12:30", "18:30"],
            )
            await _add_reminder(
                db, p9, "硝苯地平控释片", 30, "mg", "qid",
                expect_times=["08:00", "12:30", "18:00", "22:00"],
            )
            await _add_reminder(
                db, p9, "缬沙坦胶囊", 80, "mg", "q8h",
                expect_times=["08:00", "16:00", "00:00"],
            )
            await _add_reminder(
                db, p9, "瑞舒伐他汀片", 5, "mg", "qn", expect_times=["21:00"],
            )
            await _add_reminder(
                db, p9, "奥美拉唑肠溶胶囊", 20, "mg", "prn", expect_times=[],
            )
            await _add_reminder(
                db, p9, "甲钴胺片", 0.5, "mg", "qd",
                timing_note="晨起", expect_times=["07:30"],
            )
            await _add_reminder(
                db, p9, "阿托伐他汀片", 20, "mg", "bid",
                timing_note="睡前", expect_times=["21:00"],
            )
            # 今日打卡：qd 已服、bid 晚间已跳过
            today_local = datetime.now(ZoneInfo(settings.app_timezone)).date()
            await _add_checkin(db, r_qd, today_local, "08:00", "taken")
            await _add_checkin(db, r_bid, today_local, "20:00", "skipped")

            # ------------------------------------------------------------------
            # 10) 过敏冲突：青霉素过敏 + 阿莫西林；阿司匹林 + 华法林
            # ------------------------------------------------------------------
            p10 = await _create_patient(
                db, "med.safety", "测试-过敏冲突",
                ["hypertension", "hyperlipidemia"],
                allergies="青霉素", medications="华法林 2.5mg qd",
                gender="女", birth_date="1959-01-25",
            )
            await _add_reminder(db, p10, "阿莫西林胶囊", 500, "mg", "qd")
            await _add_reminder(db, p10, "阿司匹林肠溶片", 100, "mg", "qd")

            # ------------------------------------------------------------------
            # 11) 相互作用 / 剂量 / 重复用药
            # ------------------------------------------------------------------
            p11 = await _create_patient(
                db, "med.safety2", "测试-相互作用剂量",
                ["hyperlipidemia", "hypertension"],
                gender="男", birth_date="1961-06-14",
            )
            await _add_reminder(db, p11, "辛伐他汀片", 100, "mg", "qd")      # 超上限 80mg
            await _add_reminder(db, p11, "克拉霉素片", 250, "mg", "bid")     # 与辛伐他汀 major
            await _add_reminder(db, p11, "瑞舒伐他汀片", 10, "mg", "qd")     # 与红霉素 moderate
            await _add_reminder(db, p11, "红霉素片", 250, "mg", "tid")
            await _add_reminder(db, p11, "二甲双胍片", 500, "mg", "bid")     # 重复用药
            await _add_reminder(db, p11, "二甲双胍缓释片", 500, "mg", "qd")

            # ------------------------------------------------------------------
            # 12) 医疗文档：化验单 / 处方 / 出院小结 / 门诊病历
            # ------------------------------------------------------------------
            p12 = await _create_patient(
                db, "documents", "测试-医疗文档",
                ["diabetes_type2", "hypertension", "hyperlipidemia", "copd"],
                allergies="青霉素", medications="华法林 2.5mg qd",
                gender="男", birth_date="1956-08-08",
            )
            _, lab_text = await _add_document(
                db, p12, "化验单-样本4.txt", "lab_report", LAB_PARSED,
            )
            await _add_document(
                db, p12, "处方-样本5.txt", "prescription", PRESCRIPTION_PARSED,
            )
            await _add_document(
                db, p12, "出院小结-样本6.txt", "discharge_summary", DISCHARGE_PARSED,
            )
            await _add_document(
                db, p12, "门诊病历-样本7.txt", "outpatient_record", OUTPATIENT_PARSED,
            )
            _assert_lab_regex_matches(lab_text, LAB_PARSED)

            # ------------------------------------------------------------------
            # 自校验：记录数 / 预警等级分布 / 用药安全 / 文档
            # ------------------------------------------------------------------
            await _assert_counts(
                db, p1, label="单病-糖尿病", records=4,
                alerts={"yellow": 1, "orange": 1, "red": 1},
            )
            await _assert_counts(
                db, p2, label="单病-高血压", records=4,
                alerts={"yellow": 1, "orange": 1, "red": 1},
            )
            await _assert_counts(
                db, p2b, label="舒张压口径", records=1, alerts={}, abnormal=0,
            )
            await _assert_counts(
                db, p3, label="单病-高血脂", records=4,
                alerts={"yellow": 1, "orange": 1, "red": 1},
            )
            await _assert_counts(
                db, p3b, label="血脂无上下文", records=1, alerts={}, abnormal=0,
            )
            await _assert_counts(
                db, p4, label="单病-慢阻肺", records=4,
                alerts={"yellow": 1, "orange": 1, "red": 1},
            )
            await _assert_counts(
                db, p5, label="多病共存", records=4,
                alerts={"yellow": 1, "orange": 2, "red": 1},
            )
            await _assert_counts(
                db, p6, label="7天趋势", records=14, alerts={}, abnormal=4,
            )
            await _assert_counts(
                db, p7, label="30天趋势", records=50, alerts={}, abnormal=10,
            )
            await _assert_counts(
                db, p8, label="空数据", records=0, alerts={},
            )
            await _assert_counts(
                db, p9, label="用药频次", records=0, alerts={},
            )
            await _assert_counts(
                db, p10, label="过敏冲突", records=0, alerts={},
            )
            await _assert_counts(
                db, p11, label="相互作用剂量", records=0, alerts={},
            )
            await _assert_counts(
                db, p12, label="医疗文档", records=0, alerts={},
            )

            # 用药安全：频次患者无问题
            issues9 = await DrugSafetyService(db).check_patient(p9)
            if issues9:
                raise AssertionError(f"用药频次患者不应有安全问题，实际：{issues9}")

            # 过敏冲突：2 条 red（阿莫西林过敏 + 阿司匹林/华法林相互作用）
            issues10 = await DrugSafetyService(db).check_patient(p10)
            if len(issues10) != 2 or any(i["level"] != "red" for i in issues10):
                raise AssertionError(f"过敏冲突患者预期 2 条 red，实际：{issues10}")
            if not any("过敏" in i["title"] for i in issues10):
                raise AssertionError(f"缺少过敏风险：{issues10}")
            if not any("相互作用" in i["title"] for i in issues10):
                raise AssertionError(f"缺少相互作用：{issues10}")

            # 相互作用/剂量/重复：1 条 red + 3 条 orange
            issues11 = await DrugSafetyService(db).check_patient(p11)
            if len(issues11) != 4:
                raise AssertionError(f"相互作用患者预期 4 条问题，实际：{issues11}")
            if sum(1 for i in issues11 if i["level"] == "red") != 1:
                raise AssertionError(f"相互作用患者预期 1 条 red：{issues11}")
            if sum(1 for i in issues11 if i["level"] == "orange") != 3:
                raise AssertionError(f"相互作用患者预期 3 条 orange：{issues11}")
            if not any("剂量偏高" in i["title"] for i in issues11):
                raise AssertionError(f"缺少剂量偏高：{issues11}")
            if not any("重复用药" in i["title"] for i in issues11):
                raise AssertionError(f"缺少重复用药：{issues11}")

            docs = (
                await db.execute(
                    select(MedicalDocument).where(MedicalDocument.patient_id == p12.id)
                )
            ).scalars().all()
            got_types = sorted(d.doc_type for d in docs)
            expected_types = sorted(
                ["lab_report", "prescription", "discharge_summary", "outpatient_record"]
            )
            if got_types != expected_types:
                raise AssertionError(f"文档类型预期 {expected_types}，实际 {got_types}")
            print(f"[seed-test] 医疗文档: {got_types}")

            print(
                "[seed-test] 用药安全: "
                f"频次患者={len(issues9)} 过敏冲突患者={len(issues10)} "
                f"相互作用患者={len(issues11)}"
            )

            await db.commit()
            print("[seed-test] 提交完成。")
            print(
                "[seed-test] 测试账号密码统一为 test123456；"
                "demo@nurse.com 未被修改。"
            )
        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(seed_test_data())
