import base64
import gzip
import json
import struct
import uuid

import httpx
from websockets.asyncio.client import connect

from app.config import settings

ASR_HOST = "openspeech.bytedance.com"
ASR_PATH = "/api/v3/sauc/bigmodel"
TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
AUDIO_CHUNK = 3200  # 16kHz 16bit 单声道，约 100ms

# 二进制协议常量（大端序）
MSG_FULL_CLIENT = 0b0001
MSG_AUDIO_ONLY = 0b0010
MSG_SERVER_RESPONSE = 0b1001
MSG_ERROR = 0b1111
SER_NONE = 0b0000
SER_JSON = 0b0001
COMP_NONE = 0b0000
COMP_GZIP = 0b0001
FLAG_NONE = 0b0000
FLAG_LAST = 0b0010


def _frame_header(msg_type: int, flags: int, serialization: int, compression: int) -> bytes:
    b0 = (0b0001 << 4) | 0b0001  # 协议版本 1 / 头长 4
    b1 = (msg_type << 4) | flags
    b2 = (serialization << 4) | compression
    return bytes([b0, b1, b2, 0x00])


def _parse_server_frame(msg: bytes) -> dict | None:
    if len(msg) < 4:
        return None
    b1 = msg[1]
    msg_type = (b1 >> 4) & 0x0F
    flags = b1 & 0x0F
    compression = msg[2] & 0x0F
    offset = 4

    if msg_type == MSG_SERVER_RESPONSE:
        if flags & 0b0001:  # 带序列号
            offset += 4
        payload_size = struct.unpack(">I", msg[offset : offset + 4])[0]
        offset += 4
        payload = msg[offset : offset + payload_size]
        if compression == COMP_GZIP:
            payload = gzip.decompress(payload)
        data = json.loads(payload.decode("utf-8"))
        text = data.get("result", {}).get("text", "")
        return {"kind": "result", "text": text, "final": bool(flags & 0b0010)}

    if msg_type == MSG_ERROR:
        error_code = struct.unpack(">I", msg[offset : offset + 4])[0]
        offset += 4
        err_size = struct.unpack(">I", msg[offset : offset + 4])[0]
        offset += 4
        err_msg = msg[offset : offset + err_size].decode("utf-8", "replace")
        return {"kind": "error", "message": f"语音识别失败({error_code}): {err_msg}"}

    return None


class DoubaoService:
    @property
    def is_available(self) -> bool:
        return bool(settings.doubao_api_key)

    def _auth_headers(self, resource_id: str) -> dict:
        return {
            "X-Api-Key": settings.doubao_api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """语音识别：原始 PCM(16bit 单声道) → 中文文本。"""
        headers = self._auth_headers(settings.doubao_asr_resource_id)
        url = f"wss://{ASR_HOST}{ASR_PATH}"
        text = ""

        async with connect(url, additional_headers=headers, max_size=None, open_timeout=10) as ws:
            start = json.dumps(
                {
                    "user": {"uid": "caringnurse"},
                    "audio": {
                        "format": "pcm",
                        "codec": "raw",
                        "rate": sample_rate,
                        "bits": 16,
                        "channel": 1,
                    },
                    "request": {
                        "model_name": "bigmodel",
                        "enable_itn": True,
                        "enable_punc": True,
                        "result_type": "full",
                    },
                }
            ).encode("utf-8")
            await ws.send(
                _frame_header(MSG_FULL_CLIENT, FLAG_NONE, SER_JSON, COMP_NONE)
                + struct.pack(">I", len(start))
                + start
            )

            chunks = [
                pcm_bytes[i : i + AUDIO_CHUNK]
                for i in range(0, len(pcm_bytes), AUDIO_CHUNK)
            ] or [b""]
            for i, chunk in enumerate(chunks):
                flags = FLAG_LAST if i == len(chunks) - 1 else FLAG_NONE
                await ws.send(
                    _frame_header(MSG_AUDIO_ONLY, flags, SER_NONE, COMP_NONE)
                    + struct.pack(">I", len(chunk))
                    + chunk
                )

            async for msg in ws:
                if isinstance(msg, str):
                    continue  # 文本帧为异常信息，忽略
                frame = _parse_server_frame(msg)
                if frame is None:
                    continue
                if frame["kind"] == "error":
                    raise RuntimeError(frame["message"])
                if frame["text"]:
                    text = frame["text"]
                if frame["final"]:
                    break

        return text

    async def synthesize(self, text: str) -> bytes:
        """语音合成：中文文本 → mp3 字节。"""
        headers = {
            "Content-Type": "application/json",
            **self._auth_headers(settings.doubao_tts_resource_id),
        }
        body = {
            "user": {"uid": "caringnurse"},
            "req_params": {
                "text": text,
                "speaker": settings.doubao_tts_speaker,
                "sample_rate": 24000,
                "audio_params": {
                    "format": "mp3",
                    "speech_rate": 0,
                    "loudness_rate": 0,
                    "bit_rate": 64000,
                },
                "additions": json.dumps(
                    {
                        "post_process": {"pitch": 0},
                        "disable_markdown_filter": True,
                        "enable_latex_tn": False,
                    }
                ),
            },
        }
        audio_parts: list[bytes] = []

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", TTS_URL, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    code = data.get("code", 0)
                    if code not in (0, 20000000):
                        raise RuntimeError(data.get("message", f"语音合成失败({code})"))
                    if data.get("data"):
                        audio_parts.append(base64.b64decode(data["data"]))

        return b"".join(audio_parts)


doubao_service = DoubaoService()
