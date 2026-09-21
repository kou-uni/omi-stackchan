"""教師役（手元の大きいモデル）で、学習用の例を作る。

使い方: python pipeline/distill_synth.py --n 600
  出力: train/synth.jsonl（本文と、問いごとの「はい率」）

**やり方**
1. 教師役に、この用途らしい文章を作らせる（危ない例・安全な例を混ぜる）
2. 大きいモデルに判定させ、**「はい」の確率をそのまま**やわらかい正解にする
   Luce は多数決で確率を作っているが、こちらは**確率を直接読める**ので、その必要がない
   （多数決だと1件あたり15回の問い合わせが要り、600件で数時間かかる）

**大事な前提**
- **実際のライフログは一切使わない。** 全部作り物。個人の内容をモデルに覚えさせないため
- ここで作るのは**学習用**。評価は別に用意した手作りの例で行う
  （教師の答えを正解にして評価すると、「教師の真似がうまくなった度合い」しか測れない）
"""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
from pathlib import Path

from common import ollama_host

TEACHER = "qwen2.5:32b"  # 文章を作る役（Ollama）
TEACHER_JUDGE = "mlx-community/Qwen2.5-32B-Instruct-4bit"  # 判定する役（MLX・確率を直接読む）
OUT = Path(__file__).parent / "train"

QUESTIONS = {
    "others": "この文章に、本人以外の人に関する私的な情報（健康・家族・仕事・信条・住まいや居場所・人間関係など）が含まれますか？",
    "secret": "この文章に、鍵・パスワード・トークンなどの秘密情報が含まれますか？",
    "place": "この文章から、特定の場所や住所が分かりますか？",
}

# 文章のばらつきを作るための軸（同じような文ばかりにならないように）
TOPICS = [
    "技術的な気づき（測定・設計・失敗から学んだこと）",
    "仕事の打ち合わせで起きたこと",
    "家族や友人との会話",
    "健康・運動・食事の習慣",
    "買い物や移動、外出先での出来事",
    "設定ファイルや認証まわりの作業",
    "読んだ本や記事から考えたこと",
    "将来の計画や、迷っている選択",
]
STYLES = ["短い独り言", "2〜3文のメモ", "箇条書き1行", "やや長めの振り返り"]


def call(prompt: str, *, temperature: float) -> str:
    body = json.dumps(
        {
            "model": TEACHER,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": 300},
        }
    ).encode()
    req = urllib.request.Request(f"{ollama_host(prefer_remote=True)}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["response"]


def make_texts(n: int) -> list[str]:
    """この用途らしい文章を作らせる。危ない要素の有無を指定して、偏らないようにする。"""
    texts: list[str] = []
    seen: set[str] = set()
    while len(texts) < n:
        topic = random.choice(TOPICS)
        style = random.choice(STYLES)
        want = random.choice(
            [
                "誰か他人の私的な事情（健康・家族・仕事・信条・住まい）が入る",
                "鍵・パスワード・トークンのような秘密情報が入る（値は EXAMPLE-NOT-REAL のような明らかな作り物にすること）",
                "特定の場所や住所が分かる情報が入る",
                "危ない情報は何も入らない。本人の考えや学びだけ",
                "危ない情報は何も入らない。本人の行動の記録だけ",
            ]
        )
        prompt = (
            "日本語で、ある人の1日の記録から抜き出した一節を5つ作ってください。\n\n"
            f"話題: {topic}\n"
            f"書き方: {style}\n"
            f"**必ず守る条件: {want}**\n\n"
            "書き方の例（形式だけ参考にすること。内容は真似しない）:\n"
            "  相手は親の介護で今月は休みが取れないと言っていた\n"
            "  設定ファイルに API キー sk-EXAMPLE-NOT-REAL-0001 が残ったままだ\n"
            "  待ち合わせは中野駅の北口、居酒屋の2階だった\n"
            "  測ってから直す。推測で直すと、効いたかどうかが分からない\n\n"
            "注意: 実在の人名・会社名・サービス名は使わない。鍵やパスワードの値は EXAMPLE-NOT-REAL の形にする。\n"
            "説明や番号は不要。1行に1つ、5行だけ出力してください。"
        )
        for line in call(prompt, temperature=1.0).splitlines():
            line = re.sub(r"^\s*[-*・\d.、）)]+\s*", "", line).strip()
            if 12 <= len(line) <= 160 and line not in seen:
                seen.add(line)
                texts.append(line)
        print(f"  文章 {len(texts)}/{n}", end="\r", flush=True)
    print()
    return texts[:n]


def label(text: str, votes: int = 0) -> dict[str, float]:
    """大きいモデルに判定させ、「はい」の確率をそのまま返す（votes は使わない）。"""
    import os

    os.environ.setdefault("SYSONE_MODEL", TEACHER_JUDGE)
    import sysone

    decisions = sysone.ask(text, {k: sysone.Noul(v) for k, v in QUESTIONS.items()})
    return {k: round(d.probs["はい"], 4) for k, d in decisions.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--votes", type=int, default=5)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    print(f"教師役: {TEACHER} / 目標 {args.n} 件 / 多数決 {args.votes} 回")

    texts = make_texts(args.n)

    # 生成役（Ollama）と判定役（MLX）はどちらも 32B。同時に載せるとメモリが足りないので、
    # 文章を作り終えたら生成役を降ろす。
    import subprocess

    subprocess.run(["ollama", "stop", TEACHER], capture_output=True)

    path = OUT / "synth.jsonl"
    with path.open("w") as f:
        for i, text in enumerate(texts, 1):
            rates = label(text, args.votes)
            f.write(json.dumps({"text": text, **rates}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  ラベル付け {i}/{len(texts)}", end="\r", flush=True)
    print(f"\n→ {path}")


if __name__ == "__main__":
    main()
