"""接続がいつ・何回切れるかを測る。切れたら自動で繋ぎ直し、区間ごとに記録する。

使い方: python tools/conn_probe.py [総秒数=60] [音声を購読する=1]
出力: 各接続区間の 開始/切断までの秒数/受信パケット数/最後の受信からの秒数
"""
import asyncio
import sys
import time

from bleak import BleakClient

from common import AUDIO_DATA, find_omi

total = float(sys.argv[1]) if len(sys.argv) > 1 else 60
subscribe = (sys.argv[2] if len(sys.argv) > 2 else "1") == "1"


async def main():
    addr = await find_omi()
    t0 = time.monotonic()
    n = 0
    while time.monotonic() - t0 < total:
        n += 1
        gone = asyncio.Event()
        seg = {"packets": 0, "last": None}

        def on_audio(_, data):
            seg["packets"] += 1
            seg["last"] = time.monotonic()

        start = time.monotonic()
        try:
            async with BleakClient(addr, timeout=30, disconnected_callback=lambda _: gone.set()) as c:
                if subscribe:
                    await c.start_notify(AUDIO_DATA, on_audio)
                left = total - (time.monotonic() - t0)
                try:
                    await asyncio.wait_for(gone.wait(), max(left, 0.1))
                except asyncio.TimeoutError:
                    pass
                dropped = gone.is_set()  # 自分で閉じる前に判定する
        except Exception as e:  # noqa: BLE001
            print(f"#{n} connect failed after {time.monotonic() - start:.1f}s: {e}")
            await asyncio.sleep(2)
            continue
        end = time.monotonic()
        rate = seg["packets"] / max(end - start, 0.001)
        silent = f"{end - seg['last']:.1f}s" if seg["last"] else "-"
        why = "DROPPED" if dropped else "done"
        print(f"#{n} at+{start - t0:5.1f}s lived {end - start:5.1f}s packets={seg['packets']:4} "
              f"({rate:.1f}/s, 理論値50/s) silent_before_end={silent} {why}", flush=True)


asyncio.run(main())
