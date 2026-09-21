"""あなたが正解を決めるための道具。**基準を決められるのは本人だけ。**

使い方:
  python pipeline/label_cli.py                 # ペルソナが書いた文章にラベルを付ける
  python pipeline/label_cli.py --file X.jsonl  # 別のファイルに付ける
  python pipeline/label_cli.py --stats         # いまの進み具合と、モデルとの食い違いを見る

**なぜ必要か**
「社屋前で待ち合わせ」は場所が分かる記述か？ これはモデルには決められない。
**あなたのライフログにとって危ないかどうか**で決まる。
Luce（特化モデルの公開レシピ）も「本物のラベルを100〜300件用意せよ」と書いている。

操作:
  y = はい / n = いいえ / s = 判断に迷う（飛ばす） / u = 1つ戻る / q = 保存して終了

**モデルの答えは見せない。** 先に見ると、それに引きずられる（アンカリング）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT = HERE / "eval" / "gate_persona.jsonl"
OUT = HERE / "eval" / "gate_human.jsonl"

QUESTIONS = [
    ("others", "他人の私的情報が含まれる？（健康・家族・仕事・信条・住まい・人間関係）"),
    ("secret", "鍵・パスワード・トークンなどの秘密情報が含まれる？"),
    ("place", "場所が分かる？（地名・駅名・施設名・建物名など）"),
]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save(rows: list[dict]) -> None:
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))


def ask(text: str, question: str) -> str | None:
    while True:
        ans = input(f"    {question} [y/n/s/u/q] ").strip().lower()
        if ans in ("y", "n", "s", "u", "q"):
            return ans
        print("    y / n / s / u / q のどれかを入力してください")


def stats() -> None:
    if not OUT.exists():
        print("まだラベルがありません")
        return
    human = load(OUT)
    model = {r["text"]: r for r in load(DEFAULT)}
    print(f"人が付けたラベル: {len(human)} 件")
    for key, label in QUESTIONS:
        yes = sum(1 for r in human if r.get(key) is True)
        no = sum(1 for r in human if r.get(key) is False)
        both = [r for r in human if r.get(key) is not None and r["text"] in model]
        diff = sum(1 for r in both if r[key] != model[r["text"]].get(key))
        print(f"  {key:8} はい {yes:3} / いいえ {no:3} / 判断保留 {len(human) - yes - no:3}"
              f"   モデルとの食い違い {diff}/{len(both)}")
    print("\n食い違った例（モデルの判定が怪しい、または問いが曖昧なところ）:")
    shown = 0
    for r in human:
        if r["text"] not in model:
            continue
        for key, _ in QUESTIONS:
            if r.get(key) is not None and r[key] != model[r["text"]].get(key) and shown < 8:
                print(f"  {key}: 人={'はい' if r[key] else 'いいえ'} モデル={'はい' if model[r['text']][key] else 'いいえ'}"
                      f"  {r['text'][:40]}")
                shown += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=DEFAULT)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    if args.stats:
        stats()
        return

    source = load(args.file)
    done = {r["text"]: r for r in load(OUT)} if OUT.exists() else {}
    todo = [r for r in source if r["text"] not in done]
    rows = list(done.values())

    print(f"全 {len(source)} 件 / 済み {len(done)} 件 / 残り {len(todo)} 件")
    print("y=はい  n=いいえ  s=迷う（飛ばす）  u=1つ戻る  q=保存して終了\n")

    i = 0
    while i < len(todo):
        item = todo[i]
        print(f"[{len(rows) + 1}/{len(source)}] {item['text']}")
        record = {"text": item["text"]}
        if "persona" in item:
            record["persona"] = item["persona"]

        back = False
        for key, label in QUESTIONS:
            ans = ask(item["text"], label)
            if ans == "q":
                save(rows)
                print(f"\n保存しました（{len(rows)} 件）→ {OUT}")
                return
            if ans == "u":
                if rows:
                    removed = rows.pop()
                    todo.insert(i, {"text": removed["text"], "persona": removed.get("persona", "")})
                back = True
                break
            record[key] = True if ans == "y" else (False if ans == "n" else None)
        if back:
            print("  1つ戻ります\n")
            continue

        rows.append(record)
        save(rows)
        i += 1
        print()

    print(f"全部終わりました（{len(rows)} 件）→ {OUT}")


if __name__ == "__main__":
    main()
