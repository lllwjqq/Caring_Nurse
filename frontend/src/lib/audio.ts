export async function startAudioRecording(): Promise<{ stop: () => Promise<Blob> }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const audioContext = new AudioContext({ sampleRate: 16000 })
  const source = audioContext.createMediaStreamSource(stream)
  const processor = audioContext.createScriptProcessor(4096, 1, 1)
  const chunks: Float32Array[] = []

  processor.onaudioprocess = (e) => {
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
  }
  source.connect(processor)
  processor.connect(audioContext.destination)

  return {
    stop: async () => {
      // 浏览器实际采样率可能不是 16kHz（Chrome 可能忽略 sampleRate 提示），
      // 先记录真实值，统一重采样到 16k，避免 WAV 头与数据不一致导致讯飞识别为空。
      const actualRate = audioContext.sampleRate
      processor.disconnect()
      source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      try {
        await audioContext.close()
      } catch {
        /* ignore */
      }
      const total = chunks.reduce((n, c) => n + c.length, 0)
      const merged = new Float32Array(total)
      let offset = 0
      for (const c of chunks) {
        merged.set(c, offset)
        offset += c.length
      }
      return encodeWav(resample(merged, actualRate, 16000), 16000)
    },
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const pcm = new ArrayBuffer(samples.length * 2)
  const pcmView = new DataView(pcm)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    pcmView.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }

  const header = new ArrayBuffer(44)
  const view = new DataView(header)
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + pcm.byteLength, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, 'data')
  view.setUint32(40, pcm.byteLength, true)

  return new Blob([header, pcm], { type: 'audio/wav' })
}

// 线性插值重采样（降采样到 16k），保证交给讯飞的 PCM 采样率与 WAV 头一致
function resample(samples: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate <= 0 || fromRate === toRate || samples.length === 0) return samples
  const ratio = fromRate / toRate
  const outLen = Math.round(samples.length / ratio)
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio
    const idx = Math.floor(pos)
    const frac = pos - idx
    const a = samples[idx]
    const b = samples[Math.min(idx + 1, samples.length - 1)]
    out[i] = a + (b - a) * frac
  }
  return out
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}
