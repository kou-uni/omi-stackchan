"""Omi に現在時刻を渡す／いまの時刻を読む（**自前ファーム専用**）。

純正ファームにはこの受け口がないので、書き込もうとすると失敗する。

使い方:
  python tools/set_time.py          # 読むだけ
  python tools/set_time.py --set    # Mac の時刻を渡してから読み直す

受け口 19b10031:
  write 8バイト = epoch ミリ秒（リトルエンディアン）
  read 13バイト = [同期済み 1][epoch ミリ秒 8][起動ID 4]
"""
import asyncio
import datetime
import struct
import sys
import time

from bleak import BleakClient

from common import find_omi

TIME_CHAR = "19b10031-e8f2-537e-4f6c-d104768a1214"


def show(raw: bytes) -> None:
    synced, epoch_ms, boot_id = struct.unpack("<BQI", raw[:13])
    if synced:
        t = datetime.datetime.fromtimestamp(epoch_ms / 1000)
        drift = epoch_ms / 1000 - time.time()
        print(f"端末の時刻: {t:%Y-%m-%d %H:%M:%S}  ずれ {drift:+.3f}秒  起動ID {boot_id:#010x}")
    else:
        print(f"未設定（時刻を渡していない）  起動ID {boot_id:#010x}")


async def main():
    addr = await find_omi()
    async with BleakClient(addr, timeout=30) as c:
        if "--set" in sys.argv:
            await c.write_gatt_char(TIME_CHAR, struct.pack("<Q", int(time.time() * 1000)), response=True)
            print("時刻を渡した")
        show(bytes(await c.read_gatt_char(TIME_CHAR)))


asyncio.run(main())
