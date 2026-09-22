# omi-stackchan

**Omi で録った自分の1日を、手元の Mac だけで要約し、スタックチャンが声で返してくる。**
音声はクラウドに一度も出さない。

- Omi（消費者版 CV1）＝ 一緒に外へ出る**耳**
- Mac（MacBook / Mac Studio）＝ 文字起こしと要約をする**頭**。ローカル LLM
- スタックチャン ＝ 家や会場に居る**体**。表情・首・声で返す

> 「僕の1日の声は、このMacから一歩も出ていない。それでもロボットは僕を知っている」

姉妹プロジェクト: `stackchan-lab`（スタックチャン本体・DJ連携・会話サーバー）

---

## いまどこか（2026-09-19）

| | 状態 |
|---|---|
| Omi を Mac から BLE で直接見つける・読む | ✅ できた |
| ライブ音声を BLE で受けて WAV にする（クラウドなし） | ✅ できた |
| その WAV を Mac 上の Whisper で文字起こし | ✅ できた |
| **接続が途中で切れる問題** | ⚠️ 1回目は14秒で切断。2回目は60秒切れず。距離が怪しい。**最優先で潰す** |
| 本体に貯めた音声を吸い出して空にする | ✅ できた（遅い：約6時間/500MB） |
| 持ち主以外が触れないようにする（ファーム改修） | 🛠 計画中 |
| 1日分 → 要約 → スタックチャンが話す | ❓ 未着手 |

詳しくは:

- [docs/roadmap.md](docs/roadmap.md) — **やりたいこと・マイルストーン・分からないこと・検証マトリクス**
- [docs/findings.md](docs/findings.md) — 分かったこと（概要）
- [docs/event-journey.md](docs/event-journey.md) — イベント当日（9/29）の整合性と制約
- [docs/two-machines.md](docs/two-machines.md) — 2台目の Mac の使い方（いつでも切れる形にする）
- [docs/wired-recovery.md](docs/wired-recovery.md) — 有線での書き込み・復旧（調査済み・いまは保留）
- [docs/firmware-build.md](docs/firmware-build.md) — ファームを自分でビルドする（P0・実機には書き込まない）
- [docs/macbook-setup.md](docs/macbook-setup.md) — **MacBook で続きを始める手順**
- [docs/learnings.md](docs/learnings.md) — 詰まったこと・学び

## すぐ動かす

```sh
brew install opus ffmpeg
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd tools
../.venv/bin/python scan.py            # Omi が見えるか
../.venv/bin/python gatt_dump.py       # 型番・ファーム版
../.venv/bin/python live_capture.py 20 ../data/live.wav   # 20秒録る
../.venv/bin/python conn_probe.py 300  # 5分間、切れるかを測る
PATH=../.venv/bin:$PATH ./transcribe.sh ../data/live.wav
```

## 約束

- **`data/` と音声・文字起こしはコミットしない**（`.gitignore` 済み）。このリポジトリは Public
- iPhone の Omi アプリは**ペアリング解除**しておく。残っていると自動でクラウドへ同期される
- ライフログには他人の声も入る。**話させるのは本人の行動だけ。人名は落とす**
