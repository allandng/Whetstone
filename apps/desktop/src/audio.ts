// Audio helpers for voice dictation.
//
// MediaRecorder produces a compressed container that depends on the engine —
// webm/opus in Chromium (browser dev), mp4/AAC in WKWebView (the Tauri window).
// whisper-server only decodes WAV/PCM unless it was launched with `--convert`
// (which needs ffmpeg). Rather than depend on that launch flag, we convert the
// recording to 16 kHz mono 16-bit PCM WAV in the webview before uploading —
// a format whisper-server always accepts. Decoding uses the same platform
// codecs that produced the recording, so the container is always decodable.

const TARGET_SAMPLE_RATE = 16000; // whisper.cpp operates on 16 kHz audio

type AudioContextCtor = typeof AudioContext;
type OfflineAudioContextCtor = typeof OfflineAudioContext;

function audioContextCtor(): AudioContextCtor {
  const w = window as unknown as {
    AudioContext?: AudioContextCtor;
    webkitAudioContext?: AudioContextCtor;
  };
  const Ctor = w.AudioContext ?? w.webkitAudioContext;
  if (!Ctor) throw new Error("Web Audio API is unavailable in this environment.");
  return Ctor;
}

function offlineAudioContextCtor(): OfflineAudioContextCtor {
  const w = window as unknown as {
    OfflineAudioContext?: OfflineAudioContextCtor;
    webkitOfflineAudioContext?: OfflineAudioContextCtor;
  };
  const Ctor = w.OfflineAudioContext ?? w.webkitOfflineAudioContext;
  if (!Ctor) throw new Error("OfflineAudioContext is unavailable in this environment.");
  return Ctor;
}

/**
 * Convert a recorded audio Blob into a 16 kHz mono 16-bit PCM WAV Blob.
 * Throws if the audio can't be decoded (e.g. an empty/corrupt recording).
 */
export async function blobToWav(blob: Blob): Promise<Blob> {
  const bytes = await blob.arrayBuffer();
  const ctx = new (audioContextCtor())();
  let decoded: AudioBuffer;
  try {
    decoded = await ctx.decodeAudioData(bytes);
  } finally {
    void ctx.close?.();
  }
  const mono = await resampleToMono(decoded, TARGET_SAMPLE_RATE);
  return encodeWav(mono, TARGET_SAMPLE_RATE);
}

// Downmix to mono and resample to `rate` using an OfflineAudioContext, whose
// single output channel mixes the source down and renders at the target rate.
async function resampleToMono(buffer: AudioBuffer, rate: number): Promise<Float32Array> {
  const frames = Math.max(1, Math.ceil(buffer.duration * rate));
  const offline = new (offlineAudioContextCtor())(1, frames, rate);
  const src = offline.createBufferSource();
  src.buffer = buffer;
  src.connect(offline.destination);
  src.start(0);
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0);
}

/**
 * Encode mono Float32 PCM samples (range [-1, 1]) as a 16-bit PCM WAV Blob.
 * Pure function — no Web Audio dependency — so it is unit-testable directly.
 */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample; // mono
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true); // RIFF chunk size
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // audio format: PCM
  view.setUint16(22, 1, true); // channels: mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true); // byte rate
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}
