"""吸い出した生データを、時刻つきの WAV に切り分ける。

使い方: python pipeline/decode.py 2026-09-22
  入力: $LIFELOG_HOME/2026-09-22/raw.bin
  出力: $LIFELOG_HOME/2026-09-22/segments/HHMMSS.wav と segments.json

保存の形（自前ファーム 0.0.2 以降）:
  440バイトのページに [長さ][中身] を詰める
  長さ 0xFF = 時刻の印（'T','S',版,同期済み,起動ID4,経過ms4,epoch秒4）
  長さ 0    = そのページはここまで
  それ以外  = Opus のかたまり（16kHz mono / 20ms）

切り分け方:
  - 起動IDが変わったら、別の区切りにする（電源の入れ直し）
  - 時刻の印が飛んでいたら（1分以上の開きがあったら）別の区切りにする
"""
import ctypes
import json
import os
import struct
import sys
import wave
from datetime import datetime
from pathlib import Path

from common import MARKER_LEN, MARKER_TAG, PAGE, SAMPLE_RATE, day_dir

for p in ("/opt/homebrew/lib/libopus.0.dylib", "/usr/local/lib/libopus.0.dylib"):
    if os.path.exists(p):
        ctypes.CDLL(p)
        break
import opuslib  # noqa: E402

FRAME_MS = 20


def parse(raw: bytes):
    """(印, 音声のかたまり) を順番に返す。"""
    for start in range(0, len(raw), PAGE):
        page = raw[start : start + PAGE]
        pos = 0
        while pos < len(page):
            tag = page[pos]
            if tag == 0:
                break
            if tag == MARKER_TAG and page[pos + 1 : pos + 3] == b"TS":
                synced = page[pos + 4]
                boot_id, uptime_ms, epoch_s = struct.unpack("<III", page[pos + 5 : pos + 17])
                yield ("marker", (synced, boot_id, uptime_ms, epoch_s))
                pos += 1 + MARKER_LEN
            else:
                frame = page[pos + 1 : pos + 1 + tag]
                if len(frame) == tag:
                    yield ("audio", frame)
                pos += 1 + tag


def main(date: str) -> None:
    d = day_dir(date)
    raw = (d / "raw.bin").read_bytes()
    out_dir = d / "segments"
    out_dir.mkdir(exist_ok=True)

    decoder = opuslib.Decoder(SAMPLE_RATE, 1)
    segments = []
    pcm = bytearray()
    cur = None  # (epoch_s, boot_id)
    errors = 0

    def flush():
        nonlocal pcm, cur
        if cur is None or not pcm:
            pcm = bytearray()
            return
        started = datetime.fromtimestamp(cur[0])
        path = out_dir / f"{started:%H%M%S}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        segments.append(
            {
                "file": path.name,
                "start": started.isoformat(timespec="seconds"),
                "seconds": round(len(pcm) / (SAMPLE_RATE * 2), 1),
                "boot_id": f"{cur[1]:#010x}",
            }
        )
        pcm = bytearray()

    for kind, payload in parse(raw):
        if kind == "marker":
            synced, boot_id, uptime_ms, epoch_s = payload
            if not synced:
                continue  # 時刻が入っていない印は位置の手がかりにならない
            # 起動が変わった or 1分以上あいた → 区切る
            if cur is None or boot_id != cur[1] or abs(epoch_s - _expected_end(cur, pcm)) > 60:
                flush()
                cur = (epoch_s, boot_id)
        else:
            if cur is None:
                continue  # 最初の印が来るまでは捨てる（いつの音か分からないため）
            try:
                pcm.extend(decoder.decode(payload, 960))
            except Exception:  # noqa: BLE001
                errors += 1

    flush()
    (d / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1))
    total = sum(s["seconds"] for s in segments)
    print(f"{len(segments)} 区切り / 合計 {total / 60:.1f} 分 / 復号エラー {errors}")
    for s in segments[:10]:
        print(f"  {s['start']}  {s['seconds']:7.1f}秒  {s['file']}")


def _expected_end(cur, pcm) -> float:
    """いまの区切りが、音声の長さから見て何時何分まで進んでいるか。"""
    return cur[0] + len(pcm) / (SAMPLE_RATE * 2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d"))
