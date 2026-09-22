"""夜、スタックチャンが今日の学びを問いかけ、明日の備忘を渡す。

使い方:
  python pipeline/night.py 2026-09-22            # 台本を作って表示（喋らせない）
  python pipeline/night.py 2026-09-22 --speak    # 実機に喋らせる
  python pipeline/night.py --text "台本" --speak  # 台本を直接渡す

**作るもの（1日1回、30秒で聞ける長さ）**
1. 今日の要約から、**問いを1つだけ**
2. **明日の備忘を1つか2つ**

**なぜ問いを1つだけか**
まとめを読み上げられても、聞き流して終わる。
**問われると、答えようとして考える。** 記録の価値が出るのはそこ。

**安全領域から出るもの**
実機に送るのは**読み上げる文だけ**。要約そのものも、文字起こしも送らない。
送る前に関所（gate.py）と同じチェックを通す。**家の中の実機でも、通さない情報は通さない。**

実機側（stackchan-lab）の口:
  POST http://<gateway>:8779/api/speak?k=<鍵>  {"script": "..."}
  台本の記法: [happy] で表情、[pause=1.5] で間、改行で区切り
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import OLLAMA_HOST, OLLAMA_MODEL, day_dir  # noqa: E402

# stackchan-lab の操作パネル（実測: 既定ポート 8779、鍵は ~/.config/stackchan/panel-token）
STAGE_URL = __import__("os").environ.get("STACKCHAN_URL", "http://127.0.0.1:8779")
STAGE_KEY_FILE = Path.home() / ".config" / "stackchan" / "panel-token"

PROMPT = """次は、ある人の1日の記録の要約です。これを読んで、本人に向けて話しかける短い台本を書いてください。

書くもの:
1. **問いを1つだけ**。今日の記録から、本人がまだ答えを出していないこと、引っかかったまま終わったことを見つけて尋ねる
2. **明日の備忘を1つか2つ**。約束したこと、決めたのにまだ手をつけていないこと

守ること:
- 全部で**150文字以内**。声で聞くので短く
- **要約をなぞらない**。「今日は〜をしましたね」は不要
- 他人の名前は出さない（記号のまま）
- 説教しない。**問いを置いて終わる**
- 話し言葉で。親しい後輩が声をかけるくらいの距離

形式（この形をそのまま守る）:
[thinking]
（問いを1文）
[pause=1.0]
（明日の備忘を1〜2文）

1日の要約:
"""


def ask_local(prompt: str) -> str:
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.4, "num_ctx": 16384}}
    ).encode()
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"].strip()


def check_before_speaking(text: str) -> list[str]:
    """喋らせる前に、関所と同じチェックを通す。**家の中でも、通さないものは通さない。**"""
    from gate import check, check_meaning

    return check(text) + check_meaning(text)


def speak(script: str) -> None:
    # 鍵は本文ではなく URL の ?k= で渡す（stackchan-lab の stage.py の作り）
    key = STAGE_KEY_FILE.read_text().strip() if STAGE_KEY_FILE.exists() else ""
    body = json.dumps({"script": script}).encode()
    url = f"{STAGE_URL}/api/speak?k={urllib.parse.quote(key)}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print(f"実機: {json.loads(r.read())}")
    except Exception as exc:  # noqa: BLE001
        print(f"実機に届きませんでした（{type(exc).__name__}）。台本は上に出ています。")
        print(f"  スタックチャン側を先に起動してください（{STAGE_URL}）:")
        print(f"    cd ~/stackchan-lab && python -m app.dj.console  # --stage-port 8779")


def build(date: str) -> str:
    d = day_dir(date)
    src = d / "summary.anon.md"
    if not src.exists():
        src = d / "summary.md"
    if not src.exists():
        sys.exit(f"{src} がありません。先に summarize.py と anonymize.py を動かしてください")

    script = ask_local(PROMPT + src.read_text())
    # 記法以外の余計な説明を削る
    script = re.sub(r"^(台本|以下|出力)[:：].*$", "", script, flags=re.M).strip()
    (d / "night.txt").write_text(script)
    return script


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=(datetime.now()).strftime("%Y-%m-%d"))
    ap.add_argument("--speak", action="store_true")
    ap.add_argument("--text")
    args = ap.parse_args()

    script = args.text or build(args.date)
    print("--- 台本 ---")
    print(script)
    print("------------")

    spoken = re.sub(r"\[[^\]]*\]", "", script).strip()
    hits = check_before_speaking(spoken)
    if hits:
        print(f"\n⚠ 関所に引っかかりました: {' / '.join(hits)}")
        print("  喋らせません。要約を見直してください。")
        return
    print(f"（関所: 問題なし / 読み上げ {len(spoken)} 文字）")

    if args.speak:
        speak(script)


if __name__ == "__main__":
    main()
