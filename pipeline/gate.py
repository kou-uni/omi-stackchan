"""Vault に載せる前の関所。**ここを通ったものだけが安全領域の外へ出る。**

使い方:
  python pipeline/gate.py 2026-09-22            # 候補を作って、危ないものに印をつける
  python pipeline/gate.py 2026-09-22 --approve  # 承認したものを Vault へ書き出す

流れ:
  summary.md（安全領域）
    → 手元の LLM が「エージェントが学ぶべき知見」だけを抜き出す
    → 自動チェック（秘密情報・他人の情報・場所）
    → **本人が review.md を見て、要らないものを消す**
    → --approve で Vault へ

**自動チェックは補助でしかない。最後は必ず人が見る。**
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from common import OLLAMA_HOST, OLLAMA_MODEL, day_dir

VAULT = Path.home() / "Obsidian" / "ThoughtLog"

EXTRACT = """次の「1日の記録」から、**あとで自分のエージェントが参照する価値のある知見**だけを抜き出してください。

抜き出す単位（1つにつき1件。当てはまらないものは出さない）:
- insight: 自分の言葉での理解・知見
- decision: 何を選び、何を捨てたか（理由つき）
- question: 未解決のまま残っている問い
- concept: 用語の自分なりの定義

出さないもの:
- その日限りの雑事、移動、食事、単なる出来事
- 他人の情報、固有名詞（人名・会社名・店名）
- 数値だけ、状況説明だけのもの

JSON の配列だけを出力してください。各要素:
{"type":"insight|decision|question|concept","title":"主張が分かる短い題","body":"2〜8行。自分の言葉で"}

1日の記録:
"""

# 自動チェック：出してはいけないものの手がかり
PATTERNS = {
    "鍵・トークンらしき文字列": re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|xox[baprs]-[A-Za-z0-9-]{10,})"),
    "パスワードらしき記述": re.compile(r"(パスワード|passphrase|password)\s*[:：=]\s*\S+", re.I),
    "電話番号": re.compile(r"0\d{1,4}-?\d{1,4}-?\d{3,4}"),
    "メールアドレス": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "住所らしき記述": re.compile(r"(都|道|府|県).{0,10}(市|区|町|村).{0,12}\d"),
    "人名らしき敬称": re.compile(r"[一-龥ぁ-んァ-ヶA-Za-z]{2,8}(さん|くん|ちゃん|氏|部長|課長|社長|先生)"),
}


def ask(prompt: str) -> str:
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1, "num_ctx": 16384}}
    ).encode()
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())["response"]


def check(text: str) -> list[str]:
    return [name for name, pat in PATTERNS.items() if pat.search(text)]


def propose(date: str) -> None:
    d = day_dir(date)
    summary = (d / "summary.md").read_text()
    raw = ask(EXTRACT + summary)
    m = re.search(r"\[.*\]", raw, re.S)
    items = json.loads(m.group(0)) if m else []

    lines = [
        f"# {date} の候補（Vault に載せる前の確認）",
        "",
        "**残すものだけにして、`--approve` を実行してください。**",
        "消し方: 要らない項目のブロックごと削除する。",
        "",
        "⚠ の付いた項目は、自動チェックが何か見つけたものです。**必ず中身を見てください。**",
        "",
    ]
    for i, it in enumerate(items, 1):
        hits = check(it.get("title", "") + it.get("body", ""))
        flag = "⚠ " + " / ".join(hits) if hits else ""
        lines += [
            f"## {i}. [{it.get('type')}] {it.get('title')}  {flag}",
            "",
            it.get("body", "").strip(),
            "",
            "---",
            "",
        ]
    (d / "review.md").write_text("\n".join(lines))
    (d / "candidates.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    flagged = sum(1 for it in items if check(it.get("title", "") + it.get("body", "")))
    print(f"候補 {len(items)} 件（うち要注意 {flagged} 件）→ {d / 'review.md'} を見て、残すものだけにしてください")


def approve(date: str) -> None:
    d = day_dir(date)
    review = (d / "review.md").read_text()
    items = json.loads((d / "candidates.json").read_text())

    kept = [it for it in items if f"[{it['type']}] {it['title']}" in review]
    if not kept:
        print("残っている候補がありません")
        return

    folders = {"insight": "insights", "decision": "decisions", "question": "questions", "concept": "concepts"}
    written = []
    for it in kept:
        blocked = check(it["title"] + it["body"])
        if blocked:
            print(f"× 止めました（{' / '.join(blocked)}）: {it['title']}")
            continue
        folder = VAULT / folders[it["type"]]
        slug = re.sub(r"[^a-z0-9ぁ-んァ-ヶ一-龥]+", "-", it["title"].lower())[:48].strip("-")
        name = f"{date.replace('-', '')}-{slug}.md" if it["type"] == "insight" else f"{slug}.md"
        path = folder / name
        path.write_text(
            f"---\ntitle: {it['title']}\ntype: {it['type']}\nstatus: {'open' if it['type'] == 'question' else 'steady'}\n"
            f"tags: [lifelog]\nupdated: {date}\nsources:\n  - lifelog:{date}\n---\n\n# {it['title']}\n\n{it['body']}\n"
        )
        written.append(path)

    for p in written:
        print(f"✓ {p.relative_to(VAULT)}")
    print(f"{len(written)} 件を Vault へ書き出しました")


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    if "--approve" in sys.argv:
        approve(date)
    else:
        propose(date)
