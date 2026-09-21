"""その日の文字起こしから「詳細要約」を作る（手元の LLM だけ・ネットに出さない）。

使い方: python pipeline/summarize.py 2026-09-22
  入力: transcript.json
  出力: summary.md（安全領域の中に置いたままにする。Vault には入れない）

**方針**
- 残すのは**本人の行動・考え・決めたこと・約束**だけ
- **他人の名前・発言内容・連絡先・住所は落とす**（「相手」「同僚」などに置き換える）
- 出力の形は Vault の作法に寄せる（あとで蒸留しやすいように）
"""
import json
import sys
import urllib.request
from datetime import datetime

from common import OLLAMA_HOST, OLLAMA_MODEL, day_dir

PROMPT = """あなたは、本人の1日の記録を整理する補助です。文字起こしを読み、下の形式でまとめてください。

守ること:
- **本人**の行動・考え・決めたこと・約束だけを書く
- **他人の名前は書かない**。「相手」「同僚」「家族」などに置き換える
- 他人が話した内容は、本人に関係する部分だけを最小限に
- 電話番号・住所・メールアドレス・鍵やパスワードらしき文字列は**書かない**
- 聞き取れていない部分を想像で補わない。分からないものは書かない

形式:
## 今日やったこと
（時刻つきで、箇条書き）

## 考えたこと・気づき
（本人の言葉に近い形で）

## 決めたこと
（何を選び、何を捨てたか）

## 約束・やること
（誰かに約束したこと、自分で決めたタスク。期限があれば書く）

## 未解決の問い
（引っかかったまま終わったこと）

文字起こし:
"""


def ask(text: str) -> str:
    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": PROMPT + text,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 16384},
        }
    ).encode()
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())["response"]


def main(date: str) -> None:
    d = day_dir(date)
    items = json.loads((d / "transcript.json").read_text())
    if not items:
        print("文字起こしが空")
        return

    lines = [f"{x['at'][11:16]} {x['text']}" for x in items if x["text"]]
    # 長い日はいくつかに分けて要約し、最後にまとめる
    chunks, cur, size = [], [], 0
    for line in lines:
        if size + len(line) > 12000:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line)
    if cur:
        chunks.append("\n".join(cur))

    parts = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  要約 {i}/{len(chunks)} ...", flush=True)
        parts.append(ask(chunk))

    summary = parts[0] if len(parts) == 1 else ask("\n\n".join(parts))
    (d / "summary.md").write_text(f"# {date} の記録\n\n{summary}\n")
    print(f"summary.md を書いた（{len(summary)} 文字）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d"))
