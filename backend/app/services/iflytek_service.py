import base64
import hashlib
import hmac
import json
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

from websockets.asyncio.client import connect

from app.config import settings


def extract_pcm_from_wav(data: bytes) -> tuple[bytes, int]:
    """从 WAV 文件字节中提取原始 PCM（16bit little-endian）与采样率。非 WAV 时按 16kHz 原样返回。"""
    sample_rate = 16000
    pcm = data
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        idx = 12
        while idx + 8 <= len(data):
            chunk_id = data[idx : idx + 4]
            size = int.from_bytes(data[idx + 4 : idx + 8], "little")
            body = idx + 8
            if chunk_id == b"fmt " and size >= 16:
                sample_rate = int.from_bytes(data[body + 4 : body + 8], "little")
            elif chunk_id == b"data":
                pcm = data[body : body + size]
                break
            idx = body + size + (size & 1)  # chunk 按 2 字节对齐
    return pcm, sample_rate


class IFlytekService:
    IAT_HOST = "iat-api.xfyun.cn"
    IAT_PATH = "/v2/iat"
    TTS_HOST = "tts-api.xfyun.cn"
    TTS_PATH = "/v2/tts"
    AUDIO_CHUNK = 1280  # 16kHz 16bit 单声道，每帧约 40ms

    @property
    def is_available(self) -> bool:
        return bool(settings.iflytek_appid and settings.iflytek_api_key and settings.iflytek_api_secret)

    def _sign_url(self, host: str, path: str) -> str:
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            settings.iflytek_api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{settings.iflytek_api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        params = {"authorization": authorization, "date": date, "host": host}
        return f"wss://{host}{path}?{urlencode(params)}"

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """语音听写：原始 PCM(16bit 单声道) → 中文文本。"""
        url = self._sign_url(self.IAT_HOST, self.IAT_PATH)
        chunks = [pcm_bytes[i : i + self.AUDIO_CHUNK] for i in range(0, len(pcm_bytes), self.AUDIO_CHUNK)] or [b""]
        text_parts: list[str] = []

        async with connect(url, max_size=None, open_timeout=10) as ws:
            await ws.send(
                json.dumps(
                    {
                        "common": {"app_id": settings.iflytek_appid},
                        "business": {"language": "zh_cn", "domain": "iat", "accent": "mandarin", "vad_eos": 10000},
                        "data": {
                            "status": 0,
                            "format": f"audio/L16;rate={sample_rate}",
                            "encoding": "raw",
                            "audio": base64.b64encode(chunks[0]).decode(),
                        },
                    }
                )
            )
            for c in chunks[1:]:
                await ws.send(
                    json.dumps(
                        {
                            "data": {
                                "status": 1,
                                "format": f"audio/L16;rate={sample_rate}",
                                "encoding": "raw",
                                "audio": base64.b64encode(c).decode(),
                            }
                        }
                    )
                )
            await ws.send(json.dumps({"data": {"status": 2}}))

            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                if data.get("code") != 0:
                    raise RuntimeError(data.get("message", "语音识别失败"))
                payload = data.get("data", {})
                result = payload.get("result")
                if result:
                    for item in result.get("ws", []):
                        for cw in item.get("cw", []):
                            text_parts.append(cw.get("w", ""))
                if payload.get("status") == 2:
                    break

        return "".join(text_parts)

    async def synthesize(self, text: str) -> bytes:
        """语音合成：中文文本 → mp3 字节。"""
        url = self._sign_url(self.TTS_HOST, self.TTS_PATH)
        audio_parts: list[bytes] = []
        frame = {
            "common": {"app_id": settings.iflytek_appid},
            "business": {
                "aue": "lame",
                "sfl": 1,
                "auf": "audio/L16;rate=16000",
                "vcn": settings.iflytek_tts_voice,
                "tte": "utf8",
                "speed": 50,
                "volume": 50,
                "pitch": 50,
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode(),
            },
        }

        async with connect(url, max_size=None, open_timeout=10) as ws:
            await ws.send(json.dumps(frame))
            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                if data.get("code") != 0:
                    raise RuntimeError(data.get("message", "语音合成失败"))
                payload = data.get("data", {})
                audio_b64 = payload.get("audio")
                if audio_b64:
                    audio_parts.append(base64.b64decode(audio_b64))
                if payload.get("status") == 2:
                    break

        return b"".join(audio_parts)


iflytek_service = IFlytekService()
