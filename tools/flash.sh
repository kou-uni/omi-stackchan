#!/bin/zsh
# Omi に自前ファームを無線で書き込む。
#   使い方: tools/flash.sh <署名済みイメージ.bin>
#
# 重要: ブートローダーは「版数が上のもの」しか受け付けない。
#       同じ版数だと、書き込んでも黙って無視される（切り替わらない）。
#       omi.conf の CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION を毎回上げること。
#
# 手順: ①送る → ②次の起動で使う印をつける → ③再起動 → ④切り替わったか確認
set -eu
IMG=$1
SMP=${SMP:-/private/tmp/claude-501/-Users-uni/d7537899-1d55-4df1-b6f1-ab22bbd5b7e8/scratchpad/ble/bin/smpmgr}
PY=${PY:-/private/tmp/claude-501/-Users-uni/d7537899-1d55-4df1-b6f1-ab22bbd5b7e8/scratchpad/ble/bin/python}
ADDR=${OMI_ADDRESS:-$($PY -c "import asyncio;from common import find_omi;print(asyncio.run(find_omi()))" | tail -1)}

echo "== 焼く前の状態"
$SMP --ble "$ADDR" --timeout 25 image state-read | grep -E "slot=|version=|active="

echo "== ①送る"
$SMP --ble "$ADDR" --timeout 30 upgrade "$IMG"

HASH=$($SMP --ble "$ADDR" --timeout 25 image state-read | grep -A6 "slot=1" | grep -oE "[0-9A-F]{64}" | head -1)
echo "== ②次の起動で使う印: $HASH"
$SMP --ble "$ADDR" --timeout 25 image state-write "$HASH"

echo "== ③再起動"
$SMP --ble "$ADDR" --timeout 25 os reset || true
sleep 15

echo "== ④確認"
for i in 1 2 3 4 5; do
  if out=$($SMP --ble "$ADDR" --timeout 25 image state-read 2>/dev/null); then
    echo "$out" | grep -E "slot=|version=|active=|confirmed="
    break
  fi
  echo "...起動待ち"
done
