"""OCR 上传链路冒烟测试（在 backend 容器内运行）。

运行：docker compose exec -T backend python tests/ocr_upload_smoke.py
会创建一条 MedicalDocument，测试后删除数据库记录与 MinIO 对象。
"""

import asyncio
import io
import os
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import MedicalDocument  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")


def make_image(text: str = "HELLO OCR 123") -> bytes:
    image = Image.new("RGB", (720, 240), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=72)
    except Exception:
        font = ImageFont.load_default()
    draw.text((30, 70), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def main() -> None:
    login = httpx.post(
        f"{BASE}/auth/login",
        json={"email": "demo@nurse.com", "password": "demo123"},
        timeout=30,
    )
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = httpx.post(
        f"{BASE}/documents/upload",
        headers=headers,
        files={"file": ("ocr_upload_test.png", make_image(), "image/png")},
        timeout=120,
    )
    print("upload_status=", response.status_code)
    data = response.json()
    print("doc_type=", data.get("doc_type"))
    print("ocr_text=", repr((data.get("ocr_text") or "")[:300]))
    print("status=", data.get("status"))

    document_id = data.get("id")
    if document_id:
        httpx.post(f"{BASE}/documents/{document_id}/reject", headers=headers, timeout=30)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MedicalDocument).where(MedicalDocument.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if doc:
                path = doc.file_path or ""
                if "/" in path:
                    bucket, object_name = path.split("/", 1)
                    try:
                        StorageService().client.remove_object(bucket, object_name)
                    except Exception as exc:  # noqa: BLE001
                        print("minio_cleanup_fail=", exc)
                await db.delete(doc)
                await db.commit()
        print("cleaned_document=", document_id)


if __name__ == "__main__":
    asyncio.run(main())
