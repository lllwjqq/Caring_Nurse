"""OCR 归档冒烟：上传两份样本 → 确认 → 检查诊断/复诊/指标/用药与溯源。

运行：backend 目录下 `python tests/ocr_archive_smoke.py`
样本：默认取 `backend/.tmp_ocr_samples`。
"""

import json
import os
from pathlib import Path

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8080/api")
SAMPLES = Path(os.environ.get("OCR_SAMPLE_DIR", Path(__file__).resolve().parents[1] / ".tmp_ocr_samples"))

client = httpx.Client(timeout=240)
login = client.post(f"{BASE}/auth/login", json={"email": "demo@nurse.com", "password": "demo123"})
login.raise_for_status()
H = {"Authorization": f"Bearer {login.json()['access_token']}"}

created: list[dict] = []

for sample in sorted(SAMPLES.glob("*.pdf")):
    with sample.open("rb") as handle:
        response = client.post(
            f"{BASE}/documents/upload",
            headers=H,
            files={"file": (sample.name, handle.read(), "application/pdf")},
        )
    print("\nUPLOAD", sample.name, response.status_code)
    response.raise_for_status()
    doc = response.json()
    parsed = doc.get("parsed_data") or {}
    core = [m for m in parsed.get("metrics") or [] if m.get("record_type")]
    print(
        json.dumps(
            {
                "document_id": doc["id"],
                "doc_type": doc["doc_type"],
                "status": doc["status"],
                "warnings": [w.get("code") for w in parsed.get("warnings") or []],
                "ocr_meta": parsed.get("ocr_meta"),
                "metrics": len(parsed.get("metrics") or []),
                "core_metrics": len(core),
                "medications": [m.get("name") for m in parsed.get("medications") or []],
                "diagnoses": parsed.get("diagnoses"),
                "followup_at": parsed.get("followup_at"),
                "followup_department": parsed.get("followup_department"),
            },
            ensure_ascii=False,
        )
    )
    confirm = client.post(f"{BASE}/documents/{doc['id']}/confirm", headers=H, json={})
    print("CONFIRM", confirm.status_code, json.dumps(confirm.json(), ensure_ascii=False))
    confirm.raise_for_status()
    created.append({"document": doc, "actions": confirm.json().get("actions", [])})

print("\nDIAGNOSES", json.dumps(client.get(f"{BASE}/diagnoses", headers=H).json(), ensure_ascii=False))
print("APPOINTMENTS", json.dumps(client.get(f"{BASE}/appointments", headers=H).json(), ensure_ascii=False))
print("CREATED_DOCUMENT_IDS", [item["document"]["id"] for item in created])
