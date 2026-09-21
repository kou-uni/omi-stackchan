"""二段構えの判定。**軽いモデルで全部見て、疑わしいものだけ重いモデルに回す。**

使い方:
  python pipeline/sysone_cascade.py --eval    # 一段構えと比べる

**なぜこうするか**
本人の96件で測ったところ、秘密情報を100%拾えたのは 32B だけだった（3B+当て板は75%）。
だが 32B は1判定812msで、全部に使うと重い。

そこで:
  1. 軽いモデル（3B + 当て板）で全部を見る（87ms）
  2. **「はい」寄りのもの、判断が割れているものだけ**を重いモデルに回す
  3. どちらかが「危ない」と言えば、印をつける（**取りこぼしを減らす側に倒す**）

関所では**取りこぼしが最悪**なので、二段目は「打ち消す」ためではなく
「**一段目が見落としたものを拾う**」ために使う。

**境界の決め方**: 一段目の確率が下限を超えたら二段目へ。
下限を下げるほど取りこぼしは減り、時間がかかる。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

QUESTIONS = {
    "others": "この文章に、本人以外の人（相手・同僚・利用者・家族など）について分かる記述がありますか？様子、発言、予定、事情のいずれかが書かれていれば「はい」。",
    "secret": "この文章に、外部に出したくない業務上・安全上の情報が含まれますか？鍵・パスワード・ID・機器やネットワークの設定・設備の不備や弱点・社内の予定や事情のいずれかが書かれていれば「はい」。",
    "place": "この文章から、特定の場所が分かりますか？地名・駅名・施設名・建物名・棟や部屋の名称のいずれかが書かれていれば「はい」。",
}

FAST = (os.environ.get("CASCADE_FAST", "mlx-community/Qwen2.5-3B-Instruct-4bit"),
        os.environ.get("CASCADE_FAST_ADAPTER", str(HERE / "train" / "adapter-v2")))
SLOW = (os.environ.get("CASCADE_SLOW", "mlx-community/Qwen2.5-32B-Instruct-4bit"), None)

# 一段目がこの確率を超えたら、二段目に回す（低いほど取りこぼしが減り、遅くなる）
ESCALATE_ABOVE = float(os.environ.get("CASCADE_ESCALATE", "0.15"))


def _probs(model: str, adapter: str | None, texts: list[str]) -> list[dict[str, float]]:
    os.environ["SYSONE_MODEL"] = model
    if adapter:
        os.environ["SYSONE_ADAPTER"] = adapter
    else:
        os.environ.pop("SYSONE_ADAPTER", None)
    sys.modules.pop("sysone", None)
    import sysone

    out = []
    for text in texts:
        r = sysone.ask(text, {k: sysone.Noul(v) for k, v in QUESTIONS.items()})
        out.append({k: r[k].probs["はい"] for k in QUESTIONS})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--set", default="gate_human.jsonl")
    args = ap.parse_args()

    dev = [json.loads(line) for line in (HERE / "eval" / args.set).read_text().splitlines() if line.strip()]
    texts = [d["text"] for d in dev]

    t0 = time.time()
    fast = _probs(*FAST, texts)
    fast_s = time.time() - t0

    # 一段目が「怪しい」と言ったものだけ、二段目へ
    need = [i for i, p in enumerate(fast) if any(v >= ESCALATE_ABOVE for v in p.values())]
    t0 = time.time()
    slow = dict(zip(need, _probs(*SLOW, [texts[i] for i in need]))) if need else {}
    slow_s = time.time() - t0

    # 合わせ方: どちらかが高ければ高いほうを採る（取りこぼしを減らす側）
    merged = [{k: max(fast[i][k], slow.get(i, {}).get(k, 0.0)) for k in QUESTIONS} for i in range(len(dev))]

    print(f"二段構え: 一段目 {len(dev)}件 {fast_s:.1f}秒 / 二段目 {len(need)}件（{len(need) / len(dev):.0%}）{slow_s:.1f}秒")
    print(f"  合計 {fast_s + slow_s:.1f}秒 = 1文あたり {(fast_s + slow_s) / len(dev) * 1000:.0f}ms\n")

    for name, probs in (("一段目だけ", fast), ("二段構え", merged)):
        line = f"  {name:10}"
        for k in QUESTIONS:
            d = [probs[i][k] for i, it in enumerate(dev) if it[k]]
            s = [probs[i][k] for i, it in enumerate(dev) if not it[k]]
            if not d:
                continue
            th = max(0.01, min(d) * 0.8)
            line += f" {k}: 拾えた率{sum(1 for p in d if p >= 0.5) / len(d):.0%} 無駄{sum(1 for p in s if p >= th) / max(len(s), 1):.0%} |"
        print(line)


if __name__ == "__main__":
    main()
