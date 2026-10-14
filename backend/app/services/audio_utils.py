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
