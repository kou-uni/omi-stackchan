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

## 4. 出来たものの確認（P0 の完了条件）

- [ ] ビルドが最後まで通る
- [ ] 無線更新用のパッケージ（`build/dfu_application.zip`）ができる
- [ ] その中身（対象機種・版・構成）が、配布されている純正のものと一致する
- [ ] **ここで止める。実機には書き込まない**

## 5. この先（イベント後）

→ 計画は非公開（`private/firmware-plan.md`）。要点だけ:

1. まず**無改変のまま**実機に入れ直して、「焼いて戻ってくる一周」を確かめる
2. 以降は**1回につき変更は1つだけ**。焼く前に必ず本体の音声を吸い出す
3. 鍵をかける変更は**いちばん最後**。その前に「登録をやり直す」手順を実機で通しておく
4. **無線で焼き直せる仕組みには手を入れない**
