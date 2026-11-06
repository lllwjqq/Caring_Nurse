"""OCR 能力冒烟测试（在 backend 容器内运行）。

运行：
    docker compose exec -T backend python tests/ocr_smoke.py
"""

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.document_processing import DocumentService  # noqa: E402
from app.services.ocr_service import OCRService  # noqa: E402


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
    print("ocr_engine_setting=", settings.ocr_engine)
    service = OCRService()
    engine = service._get_engine()
    print("engine=", type(engine).__name__ if engine is not None else "MOCK_FALLBACK")
    print("rapidocr_available=", engine is not None)

    image_bytes = make_image()
    text = await service.extract_text(image_bytes, "ocr_test.png")
    print("ocr_text=", repr(text[:300]))
    print("contains_hello=", "HELLO" in text.upper())

    doc_text, parsed = await DocumentService().process(image_bytes, "ocr_test.png")
    print("pipeline_ocr_text=", repr(doc_text[:300]))
    print("parsed_doc_type=", parsed.get("doc_type") if isinstance(parsed, dict) else None)
    print("parsed_keys=", sorted(parsed.keys()) if isinstance(parsed, dict) else parsed)


if __name__ == "__main__":
    asyncio.run(main())
