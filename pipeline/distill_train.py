"""教師の判定を、小さいモデルに覚えさせる（LoRA）。

使い方:
  python pipeline/distill_train.py --prepare   # 学習用の形に整える
  python pipeline/distill_train.py --train     # 学習する（mlx-lm の LoRA）
  python pipeline/distill_train.py --eval      # 手作りの例で、無調整のものと比べる

**やること（正確に）**
- 土台: Qwen2.5-3B-Instruct（4bit 量子化。**重みは凍結したまま変えない**）
- 足すもの: 注意機構の射影行列に低ランク行列を足す（LoRA）。保存されるのは数十MBの差分だけ
- 学ばせ方: 「はい」「いいえ」**1語だけ**を答えさせ、その1トークンだけを損失にする
  （`--mask-prompt` で問いの部分は損失から外す）
  → **推論で確率を読む場所と、学習で最適化する場所が一致する**

**教師のラベルは確率（0〜1）**だが、mlx-lm の LoRA 学習は「どちらか1語」の形で学ぶ。
そこで **確率が中途半端なもの（0.2〜0.8）は学習から外す**。
教師自身が迷っている例を、断定として覚えさせないため。
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SYNTH = HERE / "train" / "synth.jsonl"
DATA = HERE / "train" / "data"
ADAPTER = HERE / "train" / "adapter"

BASE = "mlx-community/Qwen2.5-3B-Instruct-4bit"

QUESTIONS = {
    "others": "この文章に、本人以外の人に関する私的な情報（健康・家族・仕事・信条・住まいや居場所・人間関係など）が含まれますか？",
    "secret": "この文章に、鍵・パスワード・トークンなどの秘密情報が含まれますか？",
    "place": "この文章から、特定の場所や住所が分かりますか？",
}

SYSTEM = "あなたは判定器です。与えられた文章について、問いに選択肢のどれか1語だけで答えます。説明はしません。"

CERTAIN_LOW, CERTAIN_HIGH = 0.2, 0.8


def prepare() -> None:
    rows = [json.loads(line) for line in SYNTH.read_text().splitlines() if line.strip()]
    samples = []
    dropped = 0
    for row in rows:
        for key, question in QUESTIONS.items():
            p = float(row[key])
            if CERTAIN_LOW <= p <= CERTAIN_HIGH:
                dropped += 1
                continue  # 教師が迷っている例は使わない
            samples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": f"文章:\n{row['text']}\n\n問い: {question}\n選択肢: はい / いいえ\n答えを1語で。",
                        },
                        {"role": "assistant", "content": "はい" if p > CERTAIN_HIGH else "いいえ"},
                    ]
                }
            )

    random.seed(0)
    random.shuffle(samples)
    n_valid = max(1, len(samples) // 10)
    DATA.mkdir(parents=True, exist_ok=True)
    for name, part in (
        ("valid", samples[:n_valid]),
        ("test", samples[n_valid : n_valid * 2]),
        ("train", samples[n_valid * 2 :]),
    ):
        (DATA / f"{name}.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in part))
        print(f"  {name}: {len(part)} 件")

    yes = sum(1 for s in samples if s["messages"][-1]["content"] == "はい")
    print(f"合計 {len(samples)} 件（はい {yes} / いいえ {len(samples) - yes}）、教師が迷った {dropped} 件は除外")


def train(iters: int) -> None:
    cmd = [
        sys.executable,
        "-m",
        "mlx_lm",
        "lora",
        "--model", BASE,
        "--train",
        "--data", str(DATA),
        "--fine-tune-type", "lora",
        "--num-layers", "16",
        "--batch-size", "8",
        "--iters", str(iters),
        "--learning-rate", "1e-4",
        "--max-seq-length", "512",
        "--mask-prompt",           # 問いの部分は損失に入れない
        "--adapter-path", str(ADAPTER),
        "--steps-per-eval", "50",
        "--save-every", "100",
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def evaluate() -> None:
    """手作りの例（教師が作ったものではない）で、無調整のものと比べる。"""
    import os

    sys.path.insert(0, str(HERE))
    dev = [json.loads(line) for line in (HERE / "eval" / "gate_dev.jsonl").read_text().splitlines() if line.strip()]

    def run(model: str, adapter: str | None) -> dict:
        os.environ["SYSONE_MODEL"] = model
        if adapter:
            os.environ["SYSONE_ADAPTER"] = adapter
        else:
            os.environ.pop("SYSONE_ADAPTER", None)
        for mod in ("sysone",):
            sys.modules.pop(mod, None)
        import sysone

        ok = 0
        total = 0
        ms = 0.0
        probs_by_key: dict[str, list[tuple[float, bool]]] = {k: [] for k in QUESTIONS}
        for item in dev:
            res = sysone.ask(item["text"], {k: sysone.Noul(v) for k, v in QUESTIONS.items()})
            for key in QUESTIONS:
                p = res[key].probs["はい"]
                truth = bool(item[key])
                ok += (p >= 0.5) == truth
                total += 1
                ms += res[key].ms
                probs_by_key[key].append((p, truth))
        out = {"accuracy": ok / total, "ms": ms / total}
        for key, vals in probs_by_key.items():
            danger = [p for p, t in vals if t]
            safe = [p for p, t in vals if not t]
            th = max(0.01, min(danger) * 0.8) if danger else 0.5
            out[key] = sum(1 for p in safe if p >= th) / max(len(safe), 1)
        return out

    print("無調整の 3B を測定 ...")
    before = run(BASE, None)
    print("学習後（当て板つき）を測定 ...")
    after = run(BASE, str(ADAPTER))

    print(f"\n{'':16}{'無調整3B':>12}{'学習後3B':>12}")
    print(f"{'正解率':16}{before['accuracy']:>12.3f}{after['accuracy']:>12.3f}")
    print(f"{'1判定ms':16}{before['ms']:>12.0f}{after['ms']:>12.0f}")
    for key in QUESTIONS:
        print(f"{'無駄な印:' + key:16}{before[key]:>12.0%}{after[key]:>12.0%}")
    print("\n※ 取りこぼし0件を保つ基準での無駄な印。手作りの例40件なので参考値")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--iters", type=int, default=400)
    args = ap.parse_args()

    if args.prepare:
        prepare()
    if args.train:
        train(args.iters)
    if args.eval:
        evaluate()
