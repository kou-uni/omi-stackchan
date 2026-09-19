"""ボタンの通知と振動を確かめる（純正ファーム）。

ボタン 23ba7925: 1=1回押し 2=2回押し 5=離した（0.3〜3秒押し、または押した後の後始末）
振動 cab1ab96: 1=100ms 2=300ms 3=500ms
使い方: python tools/button_probe.py [秒数=45]
"""
import asyncio
import sys
import time

from bleak import BleakClient

from common import find_omi

BUTTON = "23ba7925-0000-1000-7450-346eac492e92"
HAPTIC = "cab1ab96-2ea5-4f4d-bb56-874b72cfc984"
NAMES = {0: "none", 1: "SINGLE_TAP", 2: "DOUBLE_TAP", 3: "LONG_TAP", 4: "PRESS", 5: "RELEASE"}
seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 45


async def main():
    addr = await find_omi()
    for attempt in range(5):
        try:
            async with BleakClient(addr, timeout=30) as c:
                t0 = time.monotonic()

                def on_button(_, data):
                    v = data[0] if data else -1
                    print(f"+{time.monotonic() - t0:6.2f}s  {NAMES.get(v, v)}  raw={bytes(data).hex()}", flush=True)

                await c.start_notify(BUTTON, on_button)
                await c.write_gatt_char(HAPTIC, bytes([1]), response=True)
                print("READY（振動したら押し始め）", flush=True)
                await asyncio.sleep(seconds)
                await c.write_gatt_char(HAPTIC, bytes([3]), response=True)
                return
        except Exception as e:  # noqa: BLE001
            print(f"connect attempt {attempt + 1}: {e}", flush=True)
            await asyncio.sleep(2)


asyncio.run(main())
