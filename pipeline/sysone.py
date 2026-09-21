"""手元で動く「判定だけ返す層」。Jev（TypeSafe の System One モデル）の設計に倣ったもの。

**何が違うのか**
ふつうの LLM は文章を1トークンずつ書く。ここでは**文章を書かせず、答えの確率だけを読む**。
モデルに問いを投げ、**答えの最初の1トークン**の確率分布を1回の計算で取り出す。
だから速く、出力の形が崩れない（決めた選択肢の外に出られない）。

**Jev から採ったもの**
- 型: Choice（どれか1つ）/ Score（段階）/ Noul（はい・いいえ）
- 確信度 = 確率分布の尖り具合。k択なら (k*最大確率 - 1)/(k-1)
  0.9超=自動でよい / 0.5〜0.9=確認を促す / 0.5未満=人に回す
- 較正（温度スケーリング）を前提にする。`sysone_eval.py` で温度と閾値を決める

**この用途で Jev と変える点**
関所の目的は「自動で捌くこと」ではなく「**危ないものを人の目に確実に届けること**」。
なので**迷ったら人に回す**（棄却は失敗ではなく、正しい動作）。

**外に出さない**: モデルは手元（MLX）。判定する文章はこの Mac から出ない。
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

# 3B でも動くが、実測では 7B のほうが明確に良かった（正解率 90.8% / 較正誤差 0.10 / 1判定179ms）。
# 3B は「他人の私的情報」をほぼ判別できず、全部に印がついてしまった。
MODEL = os.environ.get("SYSONE_MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit")
# この用途に特化させた当て板（LoRA）。指定すると、土台のモデルに差分を載せて使う。
ADAPTER = os.environ.get("SYSONE_ADAPTER") or None
def _calib_path(model: str, adapter: str | None = None) -> Path:
    """較正はモデルごとに違う。モデル名から決まるファイルを使う。

    Luce の README にあるとおり **較正は課題やモデルが変われば移らない**ので、
    1つのファイルを共用すると、別モデルの値を誤って使ってしまう。
    """
    name = model if not (adapter or ADAPTER) else f"{model}--{Path(adapter or ADAPTER).name}"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return Path(__file__).parent / f"calibration/{slug}.json"


CALIB_PATH = None  # 後方互換のため残す

_model = None
_tokenizer = None


def _ensure_loaded():
    global _model, _tokenizer
    if _model is None:
        _model, _tokenizer = load(MODEL, adapter_path=ADAPTER) if ADAPTER else load(MODEL)
    return _model, _tokenizer


@dataclass
class Question:
    """問い1つ。labels は答えの選択肢（先頭トークンが互いに違うこと）。"""

    instruction: str
    labels: list[str]
    kind: str = "choice"


def Noul(instruction: str) -> Question:  # noqa: N802  (Jev の呼び名に合わせる)
    """はい・いいえ。"""
    return Question(instruction, ["はい", "いいえ"], "noul")


def Choice(instruction: str, options: list[str]) -> Question:  # noqa: N802
    return Question(instruction, options, "choice")


def Score(instruction: str, levels: list[str] | None = None) -> Question:  # noqa: N802
    return Question(instruction, levels or ["低", "中", "高"], "score")


@dataclass
class Decision:
    value: str
    probs: dict[str, float]
    confidence: float
    ms: float
    abstain: bool = False
    detail: dict = field(default_factory=dict)


def _confidence(probs: list[float]) -> float:
    """分布の尖り具合（Jev と同じ考え方）。k択で最大確率 p のとき (k*p-1)/(k-1)。"""
    k = len(probs)
    if k < 2:
        return 1.0
    return max(0.0, min(1.0, (k * max(probs) - 1.0) / (k - 1)))


def _label_token_ids(tokenizer, labels: list[str]) -> list[int]:
    """各選択肢の「最初のトークン」を取る。重なったら使えないので、その場で気づけるようにする。"""
    ids = []
    for label in labels:
        toks = tokenizer.encode(label, add_special_tokens=False)
        if not toks:
            raise ValueError(f"選択肢をトークンにできない: {label}")
        ids.append(toks[0])
    if len(set(ids)) != len(ids):
        raise ValueError(f"選択肢の先頭トークンが重なっている: {labels}（言い換えて区別できるようにする）")
    return ids


def _load_calibration() -> dict:
    path = _calib_path(MODEL)
    if path.exists():
        return json.loads(path.read_text())
    return {"temperature": 1.0, "abstain_below": 0.5}


def ask(state: str, questions: dict[str, Question], *, system: str | None = None) -> dict[str, Decision]:
    """1つの文章に対して、複数の問いをまとめて判定する。

    文章の部分は1度だけ計算し、その結果を問いごとに使い回す（速さの肝）。
    """
    model, tokenizer = _ensure_loaded()
    calib = _load_calibration()
    temperature = float(calib.get("temperature", 1.0))
    abstain_below = float(calib.get("abstain_below", 0.5))

    sys_text = system or (
        "あなたは判定器です。与えられた文章について、問いに選択肢のどれか1語だけで答えます。説明はしません。"
    )

    # 文章までを共通の前置きにして、キャッシュを作る
    prefix = tokenizer.apply_chat_template(
        [{"role": "system", "content": sys_text}, {"role": "user", "content": f"文章:\n{state}\n\n"}],
        tokenize=False,
        add_generation_prompt=False,
    )
    prefix_ids = tokenizer.encode(prefix)
    cache = make_prompt_cache(model)
    model(mx.array([prefix_ids]), cache=cache)  # ここが使い回される計算

    results: dict[str, Decision] = {}
    for key, q in questions.items():
        t0 = time.perf_counter()
        suffix = tokenizer.apply_chat_template(
            [{"role": "user", "content": f"問い: {q.instruction}\n選択肢: {' / '.join(q.labels)}\n答えを1語で。"}],
            tokenize=False,
            add_generation_prompt=True,
        )
        suffix_ids = tokenizer.encode(suffix, add_special_tokens=False)

        branch = [c.__class__() for c in cache]  # 問いごとにキャッシュを枝分かれさせる
        for dst, src in zip(branch, cache):
            dst.update_and_fetch(src.keys[..., : src.offset, :], src.values[..., : src.offset, :])

        logits = model(mx.array([suffix_ids]), cache=branch)[0, -1]
        ids = _label_token_ids(tokenizer, q.labels)
        picked = mx.array([float(logits[i]) for i in ids]) / temperature
        probs = mx.softmax(picked).tolist()

        conf = _confidence(probs)
        best = int(max(range(len(probs)), key=lambda i: probs[i]))
        results[key] = Decision(
            value=q.labels[best],
            probs={label: round(p, 4) for label, p in zip(q.labels, probs)},
            confidence=round(conf, 4),
            ms=round((time.perf_counter() - t0) * 1000, 1),
            abstain=conf < abstain_below,
            detail={"kind": q.kind},
        )

    return results


def yes_probability(decision: Decision) -> float:
    """「はい」の確率（Noul 用）。"""
    return decision.probs.get("はい", 0.0)
