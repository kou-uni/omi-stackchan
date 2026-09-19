# MacBook で続きを始める

Mac Studio で M0 まで来た状態を、MacBook で再現する手順。**上から順に。**

---

## 1. 取ってくる

```sh
cd ~
git clone https://github.com/kou-uni/omi-stackchan.git
cd omi-stackchan
```

## 2. 道具を入れる

```sh
brew install opus ffmpeg          # Opus の復号と音量正規化
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- `mlx-whisper` は **Apple Silicon 専用**。MacBook が Apple Silicon であること
- Whisper のモデル（約1.6GB）は**初回の文字起こし時に** HF から落ちてくる。**外出前に Wi-Fi で1回回しておく**と安心

## 3. Bluetooth の権限（ここで一度詰まった）

スキャンが**エラーも出さずに止まる**なら、ほぼこれ。

- システム設定 → プライバシーとセキュリティ → **Bluetooth**
- Claude Code を動かしているアプリ（**Antigravity IDE** / ターミナル.app）を「＋」で追加してオン
- **アプリを再起動する**（しないと効かない）

## 4. iPhone の Omi アプリを外す

- iPhone の Omi アプリでデバイスの**ペアリングを解除**（または Bluetooth をオフ）
- 残っていると iPhone が先に掴む → Mac から見えない or **クラウドに同期される**

## 5. 動作確認（M0 の再現）

```sh
cd tools
../.venv/bin/python scan.py                 # 「Omi」が出る
../.venv/bin/python gatt_dump.py            # Omi CV 1 / 3.0.15
../.venv/bin/python live_capture.py 20 ../data/live.wav   # 20秒話す
PATH=../.venv/bin:$PATH ./transcribe.sh ../data/live.wav  # 文字になる
```

`DYLD_LIBRARY_PATH` は不要（`common.py` が Homebrew の libopus を直接読む）。

## 6. 次にやること

→ [roadmap.md](roadmap.md) の **M1（接続の安定）**

```sh
../.venv/bin/python conn_probe.py 300       # 5分。距離を変えて何回か
```

結果は [learnings.md](learnings.md) の「接続テスト記録」に1行ずつ足す。

---

## 注意

- **MacBook は 9/29 のイベントで DJ 用に使う本番機**でもある（`stackchan-lab`）。
  そちらのセットアップ（`./scripts/setup.sh` → `service.sh install`）が**先**。こっちで環境を壊さない
- この venv は `omi-stackchan/.venv` に閉じる。グローバルに pip install しない
