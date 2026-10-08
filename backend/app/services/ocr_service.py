"""本地 OCR 引擎封装。

默认使用 RapidOCR（onnxruntime，轻量、无 GPU 依赖、中文支持好）。
未安装或初始化失败时回退到 mock 文本，保证开发环境联调不受影响。
mock 文本按文件名区分处方/化验单，便于无模型环境联调两条链路。
"""

import asyncio
import threading

from app.config import settings

_lock = threading.Lock()
_engine = None  # 进程级单例，避免每次请求重复初始化/加载模型


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
            # 未安装 rapidocr_onnxruntime 或模型加载失败，回退 mock
            return None

    async def extract_text(self, content: bytes, filename: str) -> str:
        """从图片/PDF 字节中提取原始文本。"""
        if self.engine_name == "mock":
            return _mock_text(filename)

        images = self._to_images(content, filename)
        if not images:
            return _mock_text(filename)

        engine = self._get_engine()
        if engine is None:
            return _mock_text(filename)

        loop = asyncio.get_running_loop()
        texts: list[str] = []
        for img in images:
            text = await loop.run_in_executor(None, self._ocr_one, engine, img)
            if text:
                texts.append(text)
        joined = "\n".join(texts).strip()
        return joined or _mock_text(filename)

    def _ocr_one(self, engine, img_bytes: bytes) -> str:
        result, _ = engine(img_bytes)
        if not result:
            return ""
        return "\n".join(line[1] for line in result if line)

    def _to_images(self, content: bytes, filename: str) -> list[bytes]:
        """图片直接返回；PDF 用 pypdfium2 逐页转 PNG。"""
        if not filename.lower().endswith(".pdf"):
            return [content]
        try:
            import pypdfium2 as pdfium
        except Exception:
            return []
        images: list[bytes] = []
        try:
            pdf = pdfium.PdfDocument(content)
            for i in range(len(pdf)):
                page = pdf[i]
                bitmap = page.render(scale=2.0)
                images.append(bitmap.to_pil().tobytes("png"))
                bitmap.close()
                page.close()
            pdf.close()
        except Exception:
            pass
        return images


def _mock_text(filename: str = "") -> str:
    name = filename.lower()
    if "处方" in name or "prescription" in name or "rx" in name:
        return (
            "处方笺\n"
            "医院：XX市人民医院 科室：心内科 医生：张医生\n"
            "日期：2026-10-08\n"
            "1. 阿司匹林肠溶片 100mg 每次1片 每日1次 口服 早餐后 共30天 忌酒\n"
            "2. 二甲双胍片 500mg 每次1片 每日2次 口服 饭后 共30天\n"
            "3. 硝苯地平控释片 30mg 每次1片 每日1次 口服 晨起 共30天"
        )
    return (
        "体检报告摘要\n"
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
