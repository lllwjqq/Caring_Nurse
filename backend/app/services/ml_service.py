import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HealthRecord


class MLRiskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_risk_score(self, patient_id: int) -> float:
        result = await self.db.execute(
            select(HealthRecord)
            .where(HealthRecord.patient_id == patient_id)
            .order_by(HealthRecord.recorded_at.desc())
            .limit(30)
        )
        records = result.scalars().all()
        if len(records) < 5:
            return 0.0

        values = np.array([r.value for r in records]).reshape(-1, 1)
        abnormal_count = sum(1 for r in records if r.is_abnormal)

        try:
            clf = IsolationForest(contamination=0.2, random_state=42)
            preds = clf.fit_predict(values)
            anomaly_ratio = sum(1 for p in preds if p == -1) / len(preds)
        except Exception:
            anomaly_ratio = 0.0

        base_score = abnormal_count / len(records)
        return min(1.0, base_score * 0.6 + anomaly_ratio * 0.4)
