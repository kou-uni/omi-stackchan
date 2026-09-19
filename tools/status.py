"""本体の状態を読むだけ（書き込みなし）。1日テストの前後で比べる。

出力: 時刻 / 電池 / ストレージ状態（生バイトと uint32LE 解釈）
"""
import asyncio
import datetime
import struct

from bleak import BleakClient

from common import STORAGE_STATUS, find_omi

BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"


async def main():
    addr = await find_omi()
    async with BleakClient(addr, timeout=30) as c:
        bat = (await c.read_gatt_char(BATTERY))[0]
        raw = bytes(await c.read_gatt_char(STORAGE_STATUS))
    words = struct.unpack(f"<{len(raw) // 4}I", raw[: len(raw) // 4 * 4])
    now = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"{now} battery={bat}% storage_raw={raw.hex()} u32le={list(words)}")


asyncio.run(main())
