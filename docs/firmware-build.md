# ファームを自分でビルドする（P0）

**まだ実機には書き込まない。** ここでやるのは「純正のソースを、1文字も変えずにビルドできる」ところまで。

- 上流ソース: `~/omi-upstream`（BasedHardware/omi、MIT。`omi/firmware` だけを sparse checkout）
- 対象の版: tag `Omi_CV1_v3.0.15`（手元の実機と同じ版）
- 作業機: Mac Studio（Apple Silicon）

---

## 1. 道具（済み: 2026-09-20）

```sh
brew install --cask nrfutil
brew install west cmake ninja ccache dtc gperf
```

## 2. SDK（nRF Connect SDK 2.9.0）

```sh
# ツールチェーン（コンパイラ一式）
nrfutil install toolchain-manager
nrfutil toolchain-manager install --ncs-version v2.9.0

# ソース（Zephyr・MCUboot 等、約1.5GB）
cd ~/omi-upstream/omi/firmware
mkdir -p v2.9.0 && cd v2.9.0
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.9.0
west update
```

## 3. ビルド

```sh
cd ~/omi-upstream/omi/firmware/omi
cp omi.conf prj.conf            # Zephyr は prj.conf を見る

cd ~/omi-upstream/omi/firmware/v2.9.0
nrfutil toolchain-manager launch --ncs-version v2.9.0 --shell
# ↓ SDK のシェルの中で
west build -b omi/nrf5340/cpuapp ../omi --sysbuild -- -DBOARD_ROOT=$HOME/omi-upstream/omi/firmware
```

## 4. 出来たものの確認（P0 の完了条件）— ✅ 2026-09-20 達成

- [x] ビルドが最後まで通る
- [x] 無線更新用のパッケージ（`build/dfu_application.zip`）ができる
- [x] 構成が配布版と一致（アプリ 793,396 バイト / 無線側 175,092 バイト、対象機種・版とも同じ）
- [x] **アプリ本体のイメージは、配布版と中身まで完全に一致**（digest `7ec3b911…`）
      → 無線側（ipc_radio）だけは digest が違う。ビルド環境の差と見ている（要確認）
- [x] ここで止める。実機には書き込んでいない

### 手元の環境でハマったこと

| 症状 | 原因 | 回避 |
|---|---|---|
| `nrfutil toolchain-manager install` が無言で止まる（CPU も使わない） | macOS のキーチェーンを読みに行き、画面に出ない確認待ちになる | 配布物を直接ダウンロードし、Nordic 公開の SHA512 で照合して展開 |
| 展開したツールチェーンの python / west が動かない | `/opt/nordic/ncs/toolchains/<hash>` に置かれる前提で固定されている | コンパイラだけ使い、python と west は手元の venv（`~/ncs/venv`）で用意 |
| CMake が configure に失敗 | Homebrew の CMake 4 系は NCS 2.9 に新しすぎる | venv に `cmake==3.31.6` を入れて使う |

環境は `tools/ncs-env.sh` に固めてある（`source tools/ncs-env.sh`）。

## 5. この先（イベント後）

→ 計画は非公開（`private/firmware-plan.md`）。要点だけ:

1. まず**無改変のまま**実機に入れ直して、「焼いて戻ってくる一周」を確かめる
2. 以降は**1回につき変更は1つだけ**。焼く前に必ず本体の音声を吸い出す
3. 鍵をかける変更は**いちばん最後**。その前に「登録をやり直す」手順を実機で通しておく
4. **無線で焼き直せる仕組みには手を入れない**
