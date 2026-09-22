"""朝、話しかけると「今日やること」を返す。

使い方:
  python pipeline/morning.py                 # 台本を作って表示
  python pipeline/morning.py --speak         # 実機に喋らせる
  python pipeline/morning.py --to-hermes     # Hermes 経由で Slack へ（⑦）

**夜との違い**
夜は「問いを置いて考えさせる」。朝は「**決めさせる**」。
朝に長い話をされても困る。**やることを2〜3個、短く。**

**材料（3つ）**
1. 昨夜の備忘（`night.txt`）… 昨日の自分からの申し送り
2. Vault の未解決の問い … 引っかかったまま残っているもの
3. Backlog の期限が近い課題 … 外から決まっている締切

**優先順位の付け方**
- **期限があるものが先**（自分の気持ちより、外の締切が動かない）
- 次に、昨夜「明日やる」と決めたもの
- 問いは1つまで。**朝に問いを浴びせない**

**安全領域から出るもの**
実機に送るのは読み上げる文だけ。送る前に関所を通す。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import LIFELOG_HOME, OLLAMA_HOST, OLLAMA_MODEL  # noqa: E402
from night import STAGE_KEY_FILE, STAGE_URL, check_before_speaking, device_present  # noqa: E402

VAULT = Path.home() / "Obsidian" / "ThoughtLog"
BACKLOG = Path.home() / ".hermes" / "scripts" / "backlog.py"

PROMPT = """次の材料から、朝いちばんに本人へ話しかける短い台本を書いてください。

書くもの:
- **今日やることを2〜3個**。期限があるものを先に
- 最後に**問いを1つだけ**（なくてもよい）

守ること:
- 全部で**150文字以内**。声で聞くので短く
- **材料を読み上げない**。選んで、短く言い直す
- **課題番号（UNI-10 など）は言わない。** 声で聞くので、中身だけを言う
- **昨夜の申し送りがあれば、その中身を具体的に言う。**
  「昨日約束したことを忘れないで」のような**中身のない言い方は禁止**。
  何をするのかが分かる形で言うこと
- 他人の名前は出さない（記号のまま）
- 急かさない。朝は判断を減らしてあげる

形式（この形をそのまま守る。[pause] は1回だけ）:
[happy]
（今日やること。1〜2文。何をするのかが分かる形で）
[pause=1.0]
（あれば問いを1文）

材料:
"""


def ask_local(prompt: str) -> str:
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.4, "num_ctx": 16384}}
    ).encode()
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["response"].strip()


def last_night(today: datetime) -> str:
    """昨夜の備忘。無ければ空。"""
    for back in range(1, 4):  # 数日さかのぼって探す（毎日録れているとは限らない）
        path = LIFELOG_HOME / (today - timedelta(days=back)).strftime("%Y-%m-%d") / "night.txt"
        if path.exists():
            body = re.sub(r"\[[^\]]*\]", "", path.read_text()).strip()
            return f"【昨夜の申し送り（{back}日前）】\n{body}"
    return ""


def open_questions(limit: int = 5) -> str:
    """Vault で未解決のまま残っている問い。**新しいものから**。"""
    files = sorted(VAULT.glob("questions/*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    picked = []
    for path in files:
        text = path.read_text()
        if "status: open" not in text:
            continue
        title = re.search(r"^title:\s*(.+)$", text, re.M)
        picked.append(title.group(1).strip() if title else path.stem)
        if len(picked) >= limit:
            break
    return "【まだ答えの出ていない問い】\n" + "\n".join(f"- {t}" for t in picked) if picked else ""


def due_tasks(limit: int = 5) -> str:
    """期限のある課題。**外から決まっている締切は動かない。**"""
    if not BACKLOG.exists():
        return ""
    try:
        out = subprocess.run(
            [sys.executable, str(BACKLOG), "list", "UNI", "--open"],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:  # noqa: BLE001
        return ""
    lines = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("[ ]"):
            continue
        # 課題番号は声に乗せない。**中身だけを残す**
        body = re.sub(r"^\[ \]\s*[A-Z]+-\d+\s*", "", line)
        body = re.sub(r"^[└├─\s]+", "", body).strip()
        if body:
            lines.append(f"- {body}")
        if len(lines) >= limit:
            break
    return "【期限のある課題】\n" + "\n".join(lines) if lines else ""


def build() -> str:
    today = datetime.now()
    # 昨夜の申し送りを先頭に置く（材料の順が、そのまま重みになる）
    parts = [p for p in (last_night(today), due_tasks(), open_questions()) if p]
    if not parts:
        return "[happy]\nおはよう。今日の材料がまだ無いみたい。"
    script = ask_local(PROMPT + "\n\n".join(parts))
    return re.sub(r"^(台本|以下|出力)[:：].*$", "", script, flags=re.M).strip()


def speak(script: str) -> None:
    present = device_present()
    if present is False:
        print("\n⚠ 実機が繋がっていません。送っても音は鳴りません。")
        return
    if present is None:
        print("\n⚠ 実機の在・不在が確認できません。鳴ったかどうかは保証できません。")
    key = STAGE_KEY_FILE.read_text().strip() if STAGE_KEY_FILE.exists() else ""
    body = json.dumps({"script": script}).encode()
    req = urllib.request.Request(
        f"{STAGE_URL}/api/speak?k={urllib.parse.quote(key)}", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read())
            print("実機が受け取りました" if res.get("device") else f"送信しました: {res}")
    except Exception as exc:  # noqa: BLE001
        print(f"実機に届きませんでした（{type(exc).__name__}）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speak", action="store_true")
    ap.add_argument("--to-hermes", action="store_true", help="Hermes 経由で Slack へ（⑦・未実装）")
    args = ap.parse_args()

    script = build()
    print("--- 台本 ---")
    print(script)
    print("------------")

    spoken = re.sub(r"\[[^\]]*\]", "", script).strip()
    hits = check_before_speaking(spoken)
    if hits:
        print(f"\n⚠ 関所に引っかかりました: {' / '.join(hits)}")
        return
    print(f"（関所: 問題なし / 読み上げ {len(spoken)} 文字）")

    if args.speak:
        speak(script)
    if args.to_hermes:
        print("\n⑦ Hermes 連携はこれから。**外に出るのはここが初めて**なので、出口ゲートを先に作る")


if __name__ == "__main__":
    main()
