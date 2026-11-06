"""用药安全服务（规格 §5.7 / §10.4）。

确定性规则，不交给 LLM：
- 过敏交叉：Patient.allergies + Drug.allergy_terms
- 相互作用：DrugInteraction（major=red / moderate=orange / minor=yellow）
- 剂量：Drug.dose_min / dose_max
- 重复：同一通用名 ≥2 条
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Drug, DrugInteraction, MedicationReminder, Patient

SEVERITY_LEVEL = {"major": "red", "moderate": "orange", "minor": "yellow"}
LEVEL_RANK = {"red": 3, "orange": 2, "yellow": 1}

DOSAGE_FORM_RE = re.compile(
    r"(缓释|控释|肠溶|咀嚼|分散|泡腾|胶囊|颗粒|口服液|软膏|滴眼液|喷雾|贴剂|散|丸|片|注射液)"
)
SPEC_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|g|ml|毫克|克|毫升)", re.I)


def normalize_drug_name(name: str) -> str:
    text = (name or "").strip()
    text = SPEC_RE.sub("", text)
    text = DOSAGE_FORM_RE.sub("", text)
    return text.strip()


def split_allergies(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in re.split(r"[、,，;；\s]+", value) if p.strip()]


def parse_patient_medications(value: str | None) -> list[str]:
    """从患者长期用药文本里取药名（去掉剂量/频次）。"""
    if not value:
        return []
    names: list[str] = []
    for chunk in re.split(r"[、,，;；\n]+", value):
        match = re.match(r"\s*([\u4e00-\u9fa5A-Za-z]{2,20})", chunk)
        if match:
            names.append(match.group(1))
    return names


def _match_drug(name: str, drugs: list[Drug]) -> Drug | None:
    target = normalize_drug_name(name)
    if not target:
        return None
    for drug in drugs:
        if normalize_drug_name(drug.generic_name) == target:
            return drug
        for brand in drug.brand_names or []:
            if normalize_drug_name(str(brand)) == target:
                return drug
    return None


class DrugSafetyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_patient(self, patient: Patient) -> list[dict]:
        result = await self.db.execute(
            select(MedicationReminder).where(
                MedicationReminder.patient_id == patient.id,
                MedicationReminder.active.is_(True),
            )
        )
        reminders = list(result.scalars().all())
        meds = [{"medication_name": name} for name in parse_patient_medications(patient.medications)]
        return await self.check(patient, meds, existing_reminders=reminders)

    async def check(
        self,
        patient: Patient,
        meds: list[dict],
        existing_reminders: list[MedicationReminder] | None = None,
    ) -> list[dict]:
        all_meds: list[dict[str, Any]] = []
        for med in meds:
            name = str(
                med.get("medication_name") or med.get("name") or med.get("generic_name") or ""
            ).strip()
            if name:
                all_meds.append(
                    {
                        "name": name,
                        "dose": med.get("dose"),
                        "dose_unit": med.get("dose_unit"),
                    }
                )
        for reminder in existing_reminders or []:
            if reminder.medication_name:
                all_meds.append(
                    {
                        "name": reminder.medication_name,
                        "dose": reminder.dose,
                        "dose_unit": reminder.dose_unit,
                    }
                )
        if not all_meds:
            return []

        drug_rows = await self.db.execute(select(Drug))
        drugs = list(drug_rows.scalars().all())
        for med in all_meds:
            drug = _match_drug(med["name"], drugs)
            med["drug"] = drug
            med["canonical"] = drug.generic_name if drug else normalize_drug_name(med["name"])

        issues: list[dict] = []

        # S1 过敏交叉
        allergies = split_allergies(patient.allergies)
        for med in all_meds:
            drug = med.get("drug")
            for allergy in allergies:
                conflict = allergy in med["name"]
                if not conflict and drug:
                    conflict = any(
                        allergy in str(term) or str(term) in allergy
                        for term in (drug.allergy_terms or [])
                    )
                if conflict:
                    issues.append(
                        {
                            "level": "red",
                            "title": f"过敏风险：{med['name']}",
                            "why": f"您对「{allergy}」过敏，该药可能交叉过敏",
                            "advice": "请立即停用并联系医生更换药物",
                            "drug_names": [med["name"]],
                        }
                    )
                    break

        # S2 相互作用
        inter_rows = await self.db.execute(select(DrugInteraction))
        canonical_set = {normalize_drug_name(str(m["canonical"])) for m in all_meds}
        for item in inter_rows.scalars().all():
            a = normalize_drug_name(item.drug_a)
            b = normalize_drug_name(item.drug_b)
            if a in canonical_set and b in canonical_set:
                related = [
                    m["name"]
                    for m in all_meds
                    if normalize_drug_name(str(m["canonical"])) in (a, b)
                ]
                severity = SEVERITY_LEVEL.get(item.severity, "orange")
                issues.append(
                    {
                        "level": severity,
                        "title": f"可能相互作用：{item.drug_a} + {item.drug_b}",
                        "why": f"两药合用存在 {item.severity} 级相互作用风险",
                        "advice": item.advice,
                        "drug_names": related[:2],
                    }
                )

        # S3 剂量异常
        for med in all_meds:
            drug = med.get("drug")
            dose = med.get("dose")
            if drug is None or dose is None or drug.dose_max is None:
                continue
            unit = str(med.get("dose_unit") or "").lower()
            drug_unit = str(drug.dose_unit or "").lower()
            if unit and drug_unit and unit != drug_unit:
                continue
            try:
                dose_value = float(dose)
            except (TypeError, ValueError):
                continue
            if drug.dose_max is not None and dose_value > drug.dose_max:
                issues.append(
                    {
                        "level": "orange",
                        "title": f"剂量偏高：{med['name']}",
                        "why": f"单次 {dose_value}{med.get('dose_unit') or ''} 超过常用上限 {drug.dose_max}{drug.dose_unit or ''}",
                        "advice": "请核对处方，必要时咨询药师",
                        "drug_names": [med["name"]],
                    }
                )
            elif drug.dose_min is not None and dose_value < drug.dose_min:
                issues.append(
                    {
                        "level": "orange",
                        "title": f"剂量偏低：{med['name']}",
                        "why": f"单次 {dose_value}{med.get('dose_unit') or ''} 低于常用下限 {drug.dose_min}{drug.dose_unit or ''}",
                        "advice": "请核对处方，确认是否为医嘱剂量",
                        "drug_names": [med["name"]],
                    }
                )

        # S4 重复用药
        counts: dict[str, list[dict]] = {}
        for med in all_meds:
            key = normalize_drug_name(str(med["canonical"]))
            if key:
                counts.setdefault(key, []).append(med)
        for key, group in counts.items():
            if len(group) >= 2:
                issues.append(
                    {
                        "level": "orange",
                        "title": f"重复用药：{key}",
                        "why": f"有 {len(group)} 条用药含相同成分",
                        "advice": "请确认是否重复开药，避免叠加用药",
                        "drug_names": [m["name"] for m in group],
                    }
                )

        return sorted(issues, key=lambda x: LEVEL_RANK.get(x["level"], 0), reverse=True)
