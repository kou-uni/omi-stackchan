"""判定層を較正して、どこまで自動で任せてよいかを決める。

使い方: python pipeline/sysone_eval.py
  入力: eval/gate_dev.jsonl（作り物の例。正解ラベル付き）
  出力: sysone_calibration.json（温度と、人に回す閾値）

測るもの（Jev の公開資料と再現実装にならう）:
- **正解率**: 当たっているか
- **較正誤差 ECE**（15分割）: 「確率0.8」と言ったとき、本当に8割当たっているか
- **Brier スコア**: 確率そのものの良さ（低いほどよい）
- **棄却つきの成績**: 自信のないものを人に回したとき、残りの誤りがどれだけ減るか

**関所での方針**: 取りこぼし（危ないのに素通し）が一番まずい。
なので閾値は「自動で通す側」を厳しくし、**迷ったら人に回す**。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import sysone

DEV = Path(__file__).parent / "eval" / "gate_dev.jsonl"
OUT = None  # モデルごとに分ける（main で決める）

QUESTIONS = {
    "others": sysone.Noul("この文章に、本人以外の人に関する私的な情報（健康・家族・仕事・信条・住まいや居場所・人間関係など）が含まれますか？"),
    "secret": sysone.Noul("この文章に、鍵・パスワード・トークンなどの秘密情報が含まれますか？"),
    "place": sysone.Noul("この文章から、特定の場所や住所が分かりますか？"),
}


def collect() -> list[dict]:
    rows = []
    items = [json.loads(line) for line in DEV.read_text().splitlines() if line.strip()]
    for i, item in enumerate(items, 1):
        res = sysone.ask(item["text"], QUESTIONS)
        for key in QUESTIONS:
            rows.append(
                {
                    "key": key,
                    "yes_logit_prob": res[key].probs["はい"],
                    "truth": bool(item[key]),
                    "ms": res[key].ms,
                }
            )
        print(f"  {i}/{len(items)}", end="\r", flush=True)
    print()
    return rows


def apply_temp(p: float, t: float) -> float:
    """温度をかけ直す（確率 → ロジット → 温度で割る → 確率）。"""
    p = min(max(p, 1e-6), 1 - 1e-6)
    logit = math.log(p / (1 - p))
    return 1 / (1 + math.exp(-logit / t))


def nll(rows, t: float) -> float:
    s = 0.0
    for r in rows:
        p = apply_temp(r["yes_logit_prob"], t)
        p = min(max(p, 1e-6), 1 - 1e-6)
        s -= math.log(p) if r["truth"] else math.log(1 - p)
    return s / len(rows)


def ece(rows, t: float, bins: int = 15) -> float:
    buckets = [[] for _ in range(bins)]
    for r in rows:
        p = apply_temp(r["yes_logit_prob"], t)
        buckets[min(bins - 1, int(p * bins))].append((p, r["truth"]))
    total = len(rows)
    out = 0.0
    for b in buckets:
        if not b:
            continue
        conf = sum(p for p, _ in b) / len(b)
        acc = sum(1 for _, y in b if y) / len(b)
        out += len(b) / total * abs(conf - acc)
    return out


def brier(rows, t: float) -> float:
    return sum((apply_temp(r["yes_logit_prob"], t) - (1.0 if r["truth"] else 0.0)) ** 2 for r in rows) / len(rows)


def accuracy(rows, t: float) -> float:
    return sum(1 for r in rows if (apply_temp(r["yes_logit_prob"], t) >= 0.5) == r["truth"]) / len(rows)


def confidence_of(p: float) -> float:
    return abs(2 * p - 1)  # 2択のときの尖り具合


def fit_threshold(rows, t: float, key: str) -> dict:
    """「危ないものを取りこぼさない」ことを最優先に、印をつける基準を決める。

    関所では、危ないのに素通しするのが最悪。逆に、安全なものに印がついても
    本人が見て消すだけなので害は小さい。
    そこで **本物の危ないものが全部引っかかる位置** に基準を置き、
    そのうえで無駄な印（誤警報）がどれだけ出るかを測る。
    """
    sub = [r for r in rows if r["key"] == key]
    danger = [apply_temp(r["yes_logit_prob"], t) for r in sub if r["truth"]]
    safe = [apply_temp(r["yes_logit_prob"], t) for r in sub if not r["truth"]]
    if not danger:
        return {}

    # 危ないものの中でいちばん低い確率より、さらに少し下に基準を置く（余裕を持たせる）
    threshold = max(0.01, min(danger) * 0.8)
    false_alarm = sum(1 for p in safe if p >= threshold) / max(len(safe), 1)
    return {
        "threshold": round(threshold, 4),
        "recall": 1.0,
        "false_alarm": round(false_alarm, 3),
        "n_danger": len(danger),
        "n_safe": len(safe),
        "danger_min": round(min(danger), 3),
        "safe_max": round(max(safe), 3) if safe else None,
    }


def main() -> None:
    global OUT
    OUT = sysone._calib_path(sysone.MODEL)
    OUT.parent.mkdir(exist_ok=True)
    print(f"モデル: {sysone.MODEL}")
    print("判定中 ...")
    rows = collect()
    avg_ms = sum(r["ms"] for r in rows) / len(rows)

    best_t = min((t / 100 for t in range(50, 501, 5)), key=lambda t: nll(rows, t))

    print(f"\n判定 {len(rows)} 件 / 1件あたり平均 {avg_ms:.0f}ms")
    print(f"{'':12}{'較正前':>10}{'較正後':>10}")
    for name, fn in (("正解率", accuracy), ("較正誤差ECE", ece), ("Brier", brier)):
        print(f"{name:12}{fn(rows, 1.0):>10.3f}{fn(rows, best_t):>10.3f}")
    print(f"温度: 1.00 → {best_t:.2f}")

    print("\n問いごとの基準（危ないものを取りこぼさない位置に置く）:")
    print(f"{'問い':10}{'基準':>8}{'取りこぼし':>10}{'無駄な印':>10}{'危/安全':>10}")
    thresholds = {}
    for key in QUESTIONS:
        f = fit_threshold(rows, best_t, key)
        thresholds[key] = f
        print(f"{key:10}{f['threshold']:>8.3f}{'0件':>10}{f['false_alarm']:>10.0%}{f['n_danger']}/{f['n_safe']:>6}")

    OUT.write_text(
        json.dumps(
            {
                "model": sysone.MODEL,
                "temperature": round(best_t, 3),
                "abstain_below": 0.5,
                "thresholds": thresholds,
                "measured": {
                    "n": len(rows),
                    "accuracy": round(accuracy(rows, best_t), 3),
                    "ece": round(ece(rows, best_t), 3),
                    "brier": round(brier(rows, best_t), 3),
                    "ms_per_decision": round(avg_ms, 1),
                },
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"\n→ {OUT.name} に書いた")


if __name__ == "__main__":
    main()
