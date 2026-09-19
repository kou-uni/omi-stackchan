"""Omi のライブ音声を BLE で直接受けて WAV にする。クラウドを通らない。

使い方: python tools/live_capture.py [秒数=20] [出力=data/live.wav]

パケット = 先頭3バイトのヘッダ（連番2 + サブ連番1）+ Opus 1フレーム（16kHz mono）。
"""
import asyncio
import sys
import wave
from pathlib import Path

from common import AUDIO_DATA, SAMPLE_RATE, find_omi, load_libopus

load_libopus()
import opuslib  # noqa: E402
from bleak import BleakClient  # noqa: E402

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/live.wav")

decoder = opuslib.Decoder(SAMPLE_RATE, 1)
pcm = bytearray()
stats = {"packets": 0, "decode_err": 0}


def on_audio(_, data: bytearray):
    stats["packets"] += 1
    try:
        pcm.extend(decoder.decode(bytes(data[3:]), 960))
    except Exception:  # noqa: BLE001
        stats["decode_err"] += 1


async def main():
    addr = await find_omi()
    async with BleakClient(
        addr, timeout=30, disconnected_callback=lambda _: print("DISCONNECTED", flush=True)
    ) as c:
        await c.start_notify(AUDIO_DATA, on_audio)
        print(f"REC {seconds}s ...", flush=True)
        await asyncio.sleep(seconds)
        if c.is_connected:
            await c.stop_notify(AUDIO_DATA)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    print(f"{out}  {stats}  {len(pcm) / (SAMPLE_RATE * 2):.1f}s")


asyncio.run(main())
