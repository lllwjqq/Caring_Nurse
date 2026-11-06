"""本地 OCR 引擎封装。

默认使用 RapidOCR（onnxruntime，轻量、无 GPU 依赖、中文支持好）。
本版返回结构化 OCRResult：原文、页级文本、引擎、是否 mock、平均置信度、错误码。
- 真实引擎不可用/识别为空：返回空文本 + 错误码，不再静默伪造数据；
- 仅当显式 OCR_ENGINE=mock 时返回演示文本，并标记 is_mock=True。
"""

import asyncio
import io
import threading
from dataclasses import dataclass, field

from app.config import settings

_lock = threading.Lock()
_engine = None  # 进程级单例，避免每次请求重复初始化/加载模型


@dataclass
class OCRResult:
    text: str = ""
    pages: list[str] = field(default_factory=list)
    engine: str = ""
    is_mock: bool = False
    confidence: float | None = None
    empty: bool = True
    errors: list[str] = field(default_factory=list)


class OCRService:
    def __init__(self):
        self.engine_name = settings.ocr_engine

    def _get_engine(self):
        global _engine
        if _engine is None:
            with _lock:
                if _engine is None:
                    _engine = self._init_engine()
        return _engine

    def _init_engine(self):
        if self.engine_name == "mock":
            return None
        try:
            from rapidocr_onnxruntime import RapidOCR

            return RapidOCR()
        except Exception:
            # 未安装 rapidocr_onnxruntime 或模型加载失败
            return None

    async def extract(self, content: bytes, filename: str) -> OCRResult:
        """从图片/PDF 字节中提取文本与质量信息。"""
        if self.engine_name == "mock":
            text = _mock_text(filename)
            return OCRResult(
                text=text,
                pages=[text],
                engine="mock",
                is_mock=True,
                confidence=None,
                empty=not bool(text.strip()),
                errors=[],
            )

        engine = self._get_engine()
        if engine is None:
            return OCRResult(
                engine=self.engine_name,
                empty=True,
                errors=["ocr_engine_unavailable"],
            )

        try:
            images = self._to_images(content, filename)
        except Exception as exc:  # noqa: BLE001
            return OCRResult(
                engine=self.engine_name,
                empty=True,
                errors=[f"ocr_pdf_render_failed:{type(exc).__name__}"],
            )
        if not images:
            return OCRResult(
                engine=self.engine_name,
                empty=True,
                errors=["ocr_no_pages"],
            )

        loop = asyncio.get_running_loop()
        pages: list[str] = []
        scores: list[float] = []
        for image in images:
            text, score = await loop.run_in_executor(None, self._ocr_one, engine, image)
            pages.append(text)
            if score is not None:
                scores.append(score)

        joined = "\n\n".join(page for page in pages if page.strip()).strip()
        confidence = sum(scores) / len(scores) if scores else None
        result = OCRResult(
            text=joined,
            pages=pages,
            engine=self.engine_name,
            is_mock=False,
            confidence=round(confidence, 4) if confidence is not None else None,
            empty=not bool(joined),
            errors=[] if joined else ["ocr_empty"],
        )
        return result

    async def extract_text(self, content: bytes, filename: str) -> str:
        """兼容旧调用：只返回文本。"""
        return (await self.extract(content, filename)).text

    def _ocr_one(self, engine, img_bytes: bytes) -> tuple[str, float | None]:
        result, _ = engine(img_bytes)
        if not result:
            return "", None
        lines: list[str] = []
        scores: list[float] = []
        for line in result:
            if not line or len(line) < 2:
                continue
            lines.append(str(line[1]))
            if len(line) > 2:
                try:
                    scores.append(float(line[2]))
                except (TypeError, ValueError):
                    pass
        text = "\n".join(lines)
        score = sum(scores) / len(scores) if scores else None
        return text, score

    def _to_images(self, content: bytes, filename: str) -> list[bytes]:
        """图片直接返回；PDF 用 pypdfium2 逐页转 PNG。"""
        if not filename.lower().endswith(".pdf"):
            return [content]
        try:
            import pypdfium2 as pdfium
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("pypdfium2_unavailable") from exc

        images: list[bytes] = []
        pdf = pdfium.PdfDocument(content)
        try:
            for i in range(len(pdf)):
                page = pdf[i]
                try:
                    bitmap = page.render(scale=2.0)
                    try:
                        image = bitmap.to_pil()
                        buffer = io.BytesIO()
                        image.save(buffer, format="PNG")
                        images.append(buffer.getvalue())
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        finally:
            pdf.close()
        return images


def _mock_text(filename: str = "") -> str:
    name = filename.lower()
    if "处方" in name or "prescription" in name or "rx" in name:
        return (
            "【演示 OCR 数据】处方笺\n"
            "医院：XX市人民医院 科室：心内科 医生：张医生\n"
            "日期：2026-10-08\n"
            "1. 阿司匹林肠溶片 100mg 每次1片 每日1次 口服 早餐后 共30天 忌酒\n"
            "2. 二甲双胍片 500mg 每次1片 每日2次 口服 饭后 共30天\n"
            "3. 硝苯地平控释片 30mg 每次1片 每日1次 口服 晨起 共30天"
        )
    return (
        "【演示 OCR 数据】体检报告摘要\n"
        "姓名：患者\n"
        "检测日期：2026-10-08\n"
        "空腹血糖：6.8 mmol/L\n"
        "血压：135/85 mmHg\n"
        "心率：78 次/分\n"
        "血氧饱和度：98 %\n"
        "总胆固醇：5.2 mmol/L\n"
        "低密度脂蛋白：3.1 mmol/L\n"
        "诊断意见：血糖偏高，血脂异常，建议复查"
    )
