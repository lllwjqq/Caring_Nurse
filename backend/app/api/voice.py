import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.models import User
from app.services.audio_utils import extract_pcm_from_wav
from app.services.doubao_service import doubao_service
from app.services.iflytek_service import iflytek_service

router = APIRouter(prefix="/voice", tags=["语音"])

logger = logging.getLogger("voice")

UNAVAILABLE_DETAIL = "语音服务未配置，请在 .env 填写豆包 DOUBAO_* 或讯飞 IFLYTEK_* 凭证"


def _voice_service():
    return iflytek_service if settings.voice_provider == "iflytek" else doubao_service


class TTSRequest(BaseModel):
    text: str


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    service = _voice_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    content = await file.read()
    pcm, sample_rate = extract_pcm_from_wav(content)
    peak = 0
    rms = 0
    for i in range(0, len(pcm) - 1, 2):
        v = int.from_bytes(pcm[i : i + 2], "little", signed=True)
        if abs(v) > peak:
            peak = abs(v)
        rms += v * v
    rms = int((rms / max(1, len(pcm) // 2)) ** 0.5)
    print(
        f"[VOICE-DEBUG] filename={file.filename} content={len(content)}B "
        f"pcm={len(pcm)}B rate={sample_rate} dur_ms={len(pcm) // 2 * 1000 // max(1, sample_rate)} "
        f"peak={peak} rms={rms}",
        flush=True,
    )
    try:
        with open("/tmp/last_recording.wav", "wb") as f:
            f.write(content)
    except OSError:
        pass
    if len(pcm) < 320:
        raise HTTPException(status_code=400, detail="音频过短，请重新说话")
    text = await service.transcribe(pcm, sample_rate=sample_rate)
    if not text.strip():
        raise HTTPException(status_code=422, detail="未能识别出内容，请重试")
    return {"text": text}


@router.post("/tts")
async def tts(data: TTSRequest, user: User = Depends(get_current_user)):
    service = _voice_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="合成文本为空")
    audio = await service.synthesize(text[:800])
    if not audio:
        raise HTTPException(status_code=502, detail="语音合成失败")
    return Response(content=audio, media_type="audio/mpeg")
