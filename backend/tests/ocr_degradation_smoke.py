"""OCR 降级与不确定性规则冒烟（不写库）。"""

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_parser import normalise_parsed, validate_parsed  # noqa: E402
from app.services.document_processing import DocumentService  # noqa: E402
from app.services.ocr_service import OCRService  # noqa: E402


def white_image() -> bytes:
    image = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(image)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def main() -> None:
    # 1) 显式 mock：必须标记
    service = OCRService()
    service.engine_name = "mock"
    result = await service.extract(b"", "ocr_test.png")
    print("mock_is_mock=", result.is_mock, "has_demo_mark=", "演示 OCR" in result.text)
    assert result.is_mock and "演示 OCR" in result.text

    # 2) 引擎不可用：不返回假数据
    service = OCRService()
    service.engine_name = "rapidocr"
    service._get_engine = lambda: None  # type: ignore[method-assign]
    result = await service.extract(b"x", "ocr_test.png")
    print("unavailable_empty=", result.empty, "errors=", result.errors)
    assert result.empty and "ocr_engine_unavailable" in result.errors

    # 3) 空图：OCR 空 → status=needs_retake
    service = DocumentService()
    _, parsed = await service.process(white_image(), "blank.png")
    print("blank_status=", parsed.get("status"), "warnings=", [w.get("code") for w in parsed.get("warnings", [])])
    assert parsed.get("status") == "needs_retake"
    assert any(w.get("code") == "ocr_empty" for w in parsed.get("warnings", []))

    # 4) 数值矛盾 / 缺关键值 / 低置信度 / 非核心指标
    parsed = normalise_parsed(
        "lab_report",
        {
            "confidence": 0.9,
            "metrics": [
                {
                    "name": "血压",
                    "record_type": "blood_pressure",
                    "value": 80,
                    "systolic": 80,
                    "diastolic": 120,
                    "confidence": 0.9,
                },
                {
                    "name": "空腹血糖",
                    "record_type": "blood_glucose",
                    "value": None,
                    "confidence": 0.5,
                },
                {
                    "name": "糖化血红蛋白",
                    "record_type": None,
                    "value": 9.5,
                    "unit": "%",
                    "confidence": 0.95,
                },
            ],
        },
    )
    parsed = validate_parsed("lab_report", parsed)
    codes = [w.get("code") for w in parsed.get("warnings", [])]
    metrics = parsed.get("metrics") or []
    print("validation_codes=", codes)
    print("archiveable=", [m.get("archiveable") for m in metrics])
    assert "bp_contradiction" in codes
    assert "metric_missing_value" in codes
    assert "low_confidence" in codes
    assert metrics[0].get("archiveable") is False
    assert metrics[1].get("archiveable") is False
    assert metrics[2].get("record_type") is None
    assert metrics[2].get("archiveable") is False

    print("OVERALL PASS")


if __name__ == "__main__":
    asyncio.run(main())
