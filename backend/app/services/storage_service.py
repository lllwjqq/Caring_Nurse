import io
import re
import uuid

from minio import Minio

from app.config import settings


class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
        except Exception:
            pass

    async def upload(self, filename: str, data: io.BytesIO) -> str:
        object_name = f"{uuid.uuid4().hex}_{filename}"
        try:
            data.seek(0)
            self.client.put_object(
                settings.minio_bucket,
                object_name,
                data,
                length=-1,
                part_size=10 * 1024 * 1024,
            )
            return f"{settings.minio_bucket}/{object_name}"
        except Exception:
            return f"local/{object_name}"

    async def process_document(self, content: bytes, filename: str) -> tuple[str, dict]:
        text = ""
        try:
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                text = self._mock_ocr_image()
            elif filename.lower().endswith(".pdf"):
                text = self._mock_ocr_pdf()
            else:
                text = content.decode("utf-8", errors="ignore")[:2000]
        except Exception:
            text = "文档解析中，请稍后查看结果。"

        parsed = self._extract_health_metrics(text)
        return text, parsed

    def _mock_ocr_image(self) -> str:
        return (
            "体检报告摘要\n"
            "姓名：患者\n"
            "空腹血糖：6.8 mmol/L\n"
            "总胆固醇：5.2 mmol/L\n"
            "低密度脂蛋白：3.1 mmol/L\n"
            "血压：135/85 mmHg\n"
            "诊断意见：血糖偏高，血脂异常，建议复查"
        )

    def _mock_ocr_pdf(self) -> str:
        return self._mock_ocr_image()

    def _extract_health_metrics(self, text: str) -> dict:
        parsed: dict = {"metrics": []}
        patterns = [
            (r"空腹血糖[：:]\s*([\d.]+)\s*mmol", "blood_glucose", "mmol/L"),
            (r"血糖[：:]\s*([\d.]+)\s*mmol", "blood_glucose", "mmol/L"),
            (r"血压[：:]\s*(\d+)/(\d+)\s*mmHg", "blood_pressure", "mmHg"),
            (r"总胆固醇[：:]\s*([\d.]+)\s*mmol", "blood_lipid", "mmol/L"),
            (r"低密度脂蛋白[：:]\s*([\d.]+)\s*mmol", "blood_lipid", "mmol/L"),
        ]
        for pattern, rtype, unit in patterns:
            m = re.search(pattern, text)
            if m:
                if rtype == "blood_pressure":
                    parsed["metrics"].append({
                        "type": rtype,
                        "systolic": float(m.group(1)),
                        "diastolic": float(m.group(2)),
                        "unit": unit,
                    })
                else:
                    parsed["metrics"].append({"type": rtype, "value": float(m.group(1)), "unit": unit})
        return parsed
