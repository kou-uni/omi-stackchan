"""録音を明示的に始める／止める（**自前ファーム 0.0.3 以降**）。

純正は電源が入っている限り勝手に録り続けるが、自前ファームでは
**起動直後は止まっていて、ここから始めたときだけ録る**。電源を切ると必ず止まる。

使い方:
  python tools/record.py            # いまの状態を見る
  python tools/record.py on         # 録り始める（時刻も一緒に渡す）
  python tools/record.py off        # 止める

始めると短く1回、止めると長く1回、本体が震えて知らせる。

受け口 19b10032: write 1バイト（0=止める / 1=始める）、read 1バイト（いまの状態）
"""
import asyncio
import struct
import sys
import time

from bleak import BleakClient

from common import find_omi

RECORD_CHAR = "19b10032-e8f2-537e-4f6c-d104768a1214"
TIME_CHAR = "19b10031-e8f2-537e-4f6c-d104768a1214"

action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"


async def main():
    addr = await find_omi()
    async with BleakClient(addr, timeout=30) as c:
        if action in ("on", "start"):
            # 録り始める前に時刻を合わせる（印に正しい時刻が入るように）
            await c.write_gatt_char(TIME_CHAR, struct.pack("<Q", int(time.time() * 1000)), response=True)
            await c.write_gatt_char(RECORD_CHAR, bytes([1]), response=True)
        elif action in ("off", "stop"):
            await c.write_gatt_char(RECORD_CHAR, bytes([0]), response=True)
        elif action != "status":
            sys.exit("使い方: record.py [on|off|status]")

        state = (await c.read_gatt_char(RECORD_CHAR))[0]
        print("録音中" if state else "止まっている")


asyncio.run(main())
