# 1日を取り込んで、知見にするまで

```
Omi ──① 吸い出し──▶ raw.bin ──② 切り分け──▶ 時刻つきの WAV
                                                  │
                                            ③ 文字起こし（手元の Whisper）
                                                  ▼
                                            transcript.json
                                                  │
                                            ④ 詳細要約（手元の LLM）
                                                  ▼
                                             summary.md
                                                  │
                          ⑤ 関所: 知見の抽出 → 自動チェック → **本人の承認**
                                                  ▼
                                        ThoughtLog Vault（insights/ ほか）
```

**①〜④は安全領域の中だけで動く。** 外に出るのは⑤を通ったものだけ。

## 置き場所

既定は `~/Lifelog/<日付>/`。環境変数 `LIFELOG_HOME` で変えられる。

- **iCloud と同期するフォルダには置かない**（書類・デスクトップ）
- 将来は暗号化ボリュームに移す。そのときも `LIFELOG_HOME` を変えるだけ
- **このリポジトリには入れない**（`.gitignore` 済み）

## 使い方

```sh
# ① 吸い出し（実機から。tools/drain.py）
python tools/drain.py ~/Lifelog/2026-09-22/raw.bin

# ② 時刻つきの区切りに分ける
python pipeline/decode.py 2026-09-22

# ③ 文字起こし（ネット不要）
python pipeline/transcribe.py 2026-09-22

# ④ 詳細要約（手元の LLM）
python pipeline/summarize.py 2026-09-22

# ⑤ 知見の候補を作る → review.md を見て、要らないものを消す
python pipeline/gate.py 2026-09-22
#    残したものを Vault へ
python pipeline/gate.py 2026-09-22 --approve
```

## 関所（gate.py）が見ているもの

自動チェックは **補助**。最後は必ず本人が `review.md` を見る。

| 見つけるもの | 例 |
|---|---|
| 鍵・トークンらしき文字列 | `sk-…` `ghp_…` `AKIA…` `xoxb-…` |
| パスワードらしき記述 | 「パスワード: …」 |
| 電話番号 / メールアドレス | |
| 住所らしき記述 | |
| 人名らしき敬称 | 「〜さん」「〜部長」 |

検証済み（2026-09-21・作り物のテキストで）: 6種類すべて検出し、知見だけの文は素通しした。

**承認後も、書き出す直前にもう一度チェックする。** 引っかかったものは書き出さない。

## まだ無いもの

- 暗号化ボリューム（いまは普通のフォルダ。`LIFELOG_HOME` を移すだけで済む）
- 外向き通信の遮断（LuLu の設定）
- 保存期間の決め（音声を何日で消すか）
