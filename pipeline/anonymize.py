"""固有名詞をイニシャルに置き換える。**判定ではなく変換で解決する。**

使い方:
  python pipeline/anonymize.py 2026-09-22          # その日の要約を匿名化する
  python pipeline/anonymize.py --text "田中さんと打ち合わせ"   # 1文だけ試す

**なぜこうするか（2026-09-21 本人の基準）**

> 固有名詞が出たらだめ、イニシャルならオケ

「他人の事情が分かるか」を判定させようとすると、**人でも判断が揺れる**。
実際、ペルソナ96件にラベルを付けてもらったところ、人名が出てくる27件のうち
16件が「はい」、11件が「いいえ」で、ほぼ同じ構造の文が両方に分かれた。

**判定をやめて、変換にすれば揺れない。**
名前を消してしまえば、「その人の事情が書いてあるか」を悩む必要がなくなる。

**対応表は安全領域から出さない。**（誰がAなのかが分かってしまうため）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from common import day_dir

# 敬称つきの人名。役職だけ（「部長と打ち合わせ」）は固有名詞ではないので拾わない。
HONORIFICS = "さん|くん|ちゃん|氏|様|先生|部長|課長|社長|主任|係長|専務|常務"
ROLES_ONLY = {"部", "課", "社", "専務", "常務", "主任", "係", "先生", "店"}

# 人名ではなく職種・部署を指す語。置き換えると意味が失われるので残す
# （「製造部長」→「D部長」では何の部署か分からなくなる）
COMMON_NOUNS = {
    "製造", "営業", "技術", "開発", "総務", "人事", "経理", "品質", "生産", "保守", "設備",
    "工事", "電気", "機械", "現場", "工場", "本社", "支店", "施工", "警備", "受付",
    "オペレータ", "オペレーター", "ドライバ", "ドライバー", "スタッフ", "ヘルパー", "利用者",
    "担当", "責任", "管理", "作業", "運転", "業者", "外注", "電気工事屋", "工事屋", "配送",
    "看護", "介護", "医", "薬剤", "栄養", "事務", "研究", "指導", "教", "講師",
}

NAME_WITH_HONORIFIC = re.compile(
    rf"([一-龥ァ-ヶー]{{1,5}}|[A-Z][a-z]+)({HONORIFICS})"
)

# 明らかな組織・店舗の形
ORG = re.compile(r"([一-龥ァ-ヶA-Za-z0-9]{2,12})(株式会社|有限会社|商事|工業|製作所|銀行|病院|クリニック|大学|高校|中学校|小学校)")
ORG_PREFIX = re.compile(r"(株式会社|有限会社)([一-龥ァ-ヶA-Za-z0-9]{2,12})")

INITIALS = [chr(ord("A") + i) for i in range(26)]


def anonymize(text: str, mapping: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """固有名詞をイニシャルに置き換える。同じ名前には同じ記号を割り当てる。"""
    mapping = dict(mapping or {})

    def assign(name: str, kind: str) -> str:
        if name in mapping:
            return mapping[name]
        used = {v for v in mapping.values()}
        for letter in INITIALS:
            candidate = f"{letter}{kind}"
            if candidate not in used:
                mapping[name] = candidate
                return candidate
        mapping[name] = f"X{kind}"
        return mapping[name]

    def person(m: re.Match) -> str:
        name, honorific = m.group(1), m.group(2)
        if name in ROLES_ONLY or name in COMMON_NOUNS or len(name) == 0:
            return m.group(0)  # 役職・職種は固有名詞ではない
        return assign(name, "") + honorific

    out = NAME_WITH_HONORIFIC.sub(person, text)
    out = ORG.sub(lambda m: assign(m.group(1), "社") + m.group(2), out)
    out = ORG_PREFIX.sub(lambda m: m.group(1) + assign(m.group(2), "社"), out)
    return out, mapping


def remaining_names(text: str) -> list[str]:
    """置き換えきれなかった固有名詞らしきもの（関所が最後に見る）。"""
    hits = []
    for m in NAME_WITH_HONORIFIC.finditer(text):
        name = m.group(1)
        if name in ROLES_ONLY:
            continue
        if re.fullmatch(r"[A-Z]", name) or name in COMMON_NOUNS:
            continue  # すでにイニシャル、または職種
        hits.append(m.group(0))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--text")
    args = ap.parse_args()

    if args.text:
        out, mapping = anonymize(args.text)
        print(out)
        print(f"  対応: {mapping}")
        print(f"  残り: {remaining_names(out) or 'なし'}")
        return

    d = day_dir(args.date)
    src = d / "summary.md"
    if not src.exists():
        sys.exit(f"{src} がありません")

    # その日までに使った対応表を引き継ぐ（同じ人には同じ記号を割り当て続ける）
    table_path = d.parent / "name-table.json"  # **安全領域の外に出さない**
    mapping = json.loads(table_path.read_text()) if table_path.exists() else {}

    out, mapping = anonymize(src.read_text(), mapping)
    (d / "summary.anon.md").write_text(out)
    table_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=1))

    left = remaining_names(out)
    print(f"summary.anon.md を書いた（{len(mapping)} 名を置き換え）")
    if left:
        print(f"⚠ 置き換えきれなかったもの: {left[:10]}")
    else:
        print("固有名詞の残りなし")


if __name__ == "__main__":
    main()
