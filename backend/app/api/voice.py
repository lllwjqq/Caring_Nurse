from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.models import User
from app.services.iflytek_service import extract_pcm_from_wav, iflytek_service

router = APIRouter(prefix="/voice", tags=["语音"])


class TTSRequest(BaseModel):
    text: str


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if not iflytek_service.is_available:
        raise HTTPException(status_code=503, detail="语音识别服务未配置，请在 .env 填写讯飞 IFLYTEK_* 凭证")
    content = await file.read()
    pcm, sample_rate = extract_pcm_from_wav(content)
    if len(pcm) < 320:
        raise HTTPException(status_code=400, detail="音频过短，请重新说话")
    text = await iflytek_service.transcribe(pcm, sample_rate=sample_rate)
    if not text.strip():
        raise HTTPException(status_code=422, detail="未能识别出内容，请重试")
    return {"text": text}


@router.post("/tts")
async def tts(data: TTSRequest, user: User = Depends(get_current_user)):
    if not iflytek_service.is_available:
        raise HTTPException(status_code=503, detail="语音合成服务未配置，请在 .env 填写讯飞 IFLYTEK_* 凭证")
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="合成文本为空")
    audio = await iflytek_service.synthesize(text[:800])
    if not audio:
        raise HTTPException(status_code=502, detail="语音合成失败")
    return Response(content=audio, media_type="audio/mpeg")
