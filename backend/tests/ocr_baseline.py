"""OCR baseline：对样本目录逐份跑当前 OCR + 抽取，输出 JSON（不写库）。

运行（backend 容器内）：
    OCR_SAMPLE_DIR=/app/.tmp_ocr_samples python tests/ocr_baseline.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_processing import DocumentService  # noqa: E402


async def main() -> None:
    sample_dir = Path(os.environ.get("OCR_SAMPLE_DIR", "/app/.tmp_ocr_samples"))
    service = DocumentService()
    records: list[dict] = []
    for path in sorted(sample_dir.glob("*.pdf")):
        text, parsed = await service.process(path.read_bytes(), path.name)
        records.append(
            {
                "file": path.name,
                "ocr_chars": len(text),
                "doc_type": parsed.get("doc_type"),
                "confidence": parsed.get("confidence"),
                "metrics": [
                    {
                        "name": m.get("name"),
                        "value": m.get("value"),
                        "unit": m.get("unit"),
                        "record_type": m.get("record_type"),
                        "confidence": m.get("confidence"),
                    }
                    for m in (parsed.get("metrics") or [])
                ],
                "medications": [
                    m.get("name") or m.get("generic_name")
                    for m in (parsed.get("medications") or [])
                ],
                "diagnoses": parsed.get("diagnoses"),
                "doctor_orders": parsed.get("doctor_orders"),
                "followup_at": parsed.get("followup_at"),
                "family_history": parsed.get("family_history"),
                "personal_history": parsed.get("personal_history"),
                "warnings": parsed.get("warnings"),
                "needs_retake": parsed.get("needs_retake"),
                "ocr_meta": parsed.get("ocr_meta"),
                "ocr_excerpt": text[:400],
            }
        )
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    print(payload)
    Path("/app/tests/baseline_ocr.json").write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
