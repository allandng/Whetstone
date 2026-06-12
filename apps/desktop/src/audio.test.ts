import { describe, it, expect } from "vitest";
import { encodeWav } from "./audio";

async function bytes(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer());
}

const ascii = (view: DataView, offset: number, len: number) =>
  Array.from({ length: len }, (_, i) => String.fromCharCode(view.getUint8(offset + i))).join("");

describe("encodeWav", () => {
  it("produces a 16-bit mono PCM WAV with a correct header", async () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1]);
    const blob = encodeWav(samples, 16000);

    expect(blob.type).toBe("audio/wav");
    // 44-byte header + 2 bytes per sample.
    expect(blob.size).toBe(44 + samples.length * 2);

    const view = await bytes(blob);
    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(ascii(view, 8, 4)).toBe("WAVE");
    expect(ascii(view, 12, 4)).toBe("fmt ");
    expect(ascii(view, 36, 4)).toBe("data");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000); // sample rate
    expect(view.getUint16(34, true)).toBe(16); // bits per sample
    expect(view.getUint32(40, true)).toBe(samples.length * 2); // data size
  });

  it("clamps and scales samples to full-range int16", async () => {
    const view = await bytes(encodeWav(new Float32Array([1, -1, 2, -2, 0]), 16000));
    expect(view.getInt16(44, true)).toBe(0x7fff); // +1.0 -> max
    expect(view.getInt16(46, true)).toBe(-0x8000); // -1.0 -> min
    expect(view.getInt16(48, true)).toBe(0x7fff); // +2.0 clamped to +1.0
    expect(view.getInt16(50, true)).toBe(-0x8000); // -2.0 clamped to -1.0
    expect(view.getInt16(52, true)).toBe(0); // silence
  });
});
