"""録った音声から、**指定した時間帯を消す**。

使い方:
  python pipeline/redact.py 2026-09-29 --from 19:20 --to 19:45
  python pipeline/redact.py 2026-09-29 --from 19:20 --to 19:45 --dry

**なぜ要るか（2026-09-23）**
イベントの口上に「**嫌な方は言ってください。その分は消します**」という出口を入れる。
言った以上、**消せなければ嘘になる。**

**どこまで消せるか（正直に）**

| | 可否 |
|---|---|
| 本体（Omi）の中で、一部だけ消す | **できない。** 全消しのみ（ファームの作り） |
| 吸い出したあと、Mac の上で時間帯を消す | **できる**（これがこの道具） |
| 消せる細かさ | **約1分**（時刻の印が1分ごとに入っているため） |

つまり運用はこうなる:
  1. 会場では止めるだけ（本体の電源を切る）
  2. 帰宅後に吸い出す
  3. **文字起こしの前に、この道具でその時間帯を消す**
  4. 消してから、要約に進む

**文字起こしの前に消すこと。** 文字になってからでは、消し漏れが増える。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import day_dir  # noqa: E402


def parse_time(date: str, hhmm: str) -> datetime:
    return datetime.strptime(f"{date} {hhmm}", "%Y-%m-%d %H:%M")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--from", dest="start", required=True, help="消し始める時刻 (例 19:20)")
    ap.add_argument("--to", dest="end", required=True, help="消し終える時刻 (例 19:45)")
    ap.add_argument("--dry", action="store_true", help="消さずに、何が消えるかだけ見る")
    args = ap.parse_args()

    d = day_dir(args.date)
    seg_file = d / "segments.json"
    if not seg_file.exists():
        sys.exit(f"{seg_file} がありません。先に decode.py を動かしてください")

    start = parse_time(args.date, args.start)
    end = parse_time(args.date, args.end)
    if end <= start:
        sys.exit("終わりが始まりより前になっています")

    segments = json.loads(seg_file.read_text())
    removed, kept = [], []
    for seg in segments:
        s = datetime.fromisoformat(seg["start"])
        e = s + timedelta(seconds=float(seg["seconds"]))
        (removed if (s < end and e > start) else kept).append(seg)

    print(f"消す範囲: {start:%H:%M} 〜 {end:%H:%M}")
    print(f"  消える区切り: {len(removed)} 件 / 残る区切り: {len(kept)} 件")
    for seg in removed:
        print(f"    {seg['start'][11:19]}  {seg['seconds']:6.1f}秒  {seg['file']}")

    if args.dry:
        print("\n（--dry なので、何も消していません）")
        return
    if not removed:
        print("該当する区切りがありません")
        return

    # 消した記録は残す（何を消したかが分からなくなるのを防ぐ）
    log = d / "redacted.log"
    with log.open("a") as f:
        for seg in removed:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t削除\t{seg['start']}\t{seg['seconds']}秒\t{seg['file']}\n")

    for seg in removed:
        path = d / "segments" / seg["file"]
        if path.exists():
            path.unlink()
    seg_file.write_text(json.dumps(kept, ensure_ascii=False, indent=1))

    # 生データも消す（ここを残すと、消したことにならない）
    raw = d / "raw.bin"
    if raw.exists():
        raw.unlink()
        print(f"\n生データ（raw.bin）も消しました。**区切り済みの音声だけが残ります**")

    print(f"{len(removed)} 件を消しました。記録: {log.name}")
    print("※ 本体（Omi）側は全消ししかできません。この道具は吸い出したあとの Mac 上の話です")


if __name__ == "__main__":
    main()
