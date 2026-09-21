"""区切りごとに文字起こしする（手元の Whisper・ネット不要）。

使い方: python pipeline/transcribe.py 2026-09-22
  入力: segments/*.wav と segments.json
  出力: transcript.json（区切りごとの発話に、実際の時刻を付けたもの）

**音量をそろえてから渡す。** Omi の録音は小さめ（平均 -46dB）なので、そのままだと拾い落とす。
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from common import WHISPER_MODEL, day_dir, force_offline

force_offline()


def normalize(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af", "loudnorm", str(dst)],
        check=True,
    )


def main(date: str) -> None:
    d = day_dir(date)
    segments = json.loads((d / "segments.json").read_text())
    import mlx_whisper  # 重いので必要になってから読む

    out = []
    for seg in segments:
        src = d / "segments" / seg["file"]
        norm = d / "segments" / f"norm-{seg['file']}"
        normalize(src, norm)
        result = mlx_whisper.transcribe(str(norm), path_or_hf_repo=WHISPER_MODEL, language="ja")
        base = datetime.fromisoformat(seg["start"])
        for s in result.get("segments", []):
            out.append(
                {
                    "at": (base + timedelta(seconds=float(s["start"]))).isoformat(timespec="seconds"),
                    "seconds": round(float(s["end"]) - float(s["start"]), 1),
                    "text": s["text"].strip(),
                }
            )
        norm.unlink(missing_ok=True)
        print(f"  {seg['file']} 完了", flush=True)

    (d / "transcript.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    chars = sum(len(x["text"]) for x in out)
    print(f"{len(out)} 発話 / 合計 {chars} 文字 → transcript.json")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d"))
