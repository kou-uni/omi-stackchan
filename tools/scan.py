"""周囲の BLE 端末を一覧する。Omi が見えるかの最初の確認用。

止まったまま返ってこない → macOS の Bluetooth 権限がない（docs/macbook-setup.md）
"""
import asyncio

from bleak import BleakScanner


async def main():
    devices = await asyncio.wait_for(BleakScanner.discover(timeout=10, return_adv=True), 30)
    for addr, (dev, adv) in devices.items():
        name = dev.name or adv.local_name
        if name:
            print(f"{name:24} {addr} rssi={adv.rssi} {adv.service_uuids[:3]}")


asyncio.run(main())
