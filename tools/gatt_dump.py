"""Omi に接続し、全サービスと読める値を出す（読み取りのみ）。型番・ファーム版の確認に使う。"""
import asyncio

from bleak import BleakClient

from common import find_omi


async def main():
    addr = await find_omi()
    async with BleakClient(addr, timeout=30) as c:
        for s in c.services:
            print("SVC", s.uuid, s.description)
            for ch in s.characteristics:
                v = ""
                if "read" in ch.properties:
                    try:
                        b = await c.read_gatt_char(ch)
                        v = b.decode() if s.uuid.startswith("0000180a") else b.hex()
                    except Exception as e:  # noqa: BLE001
                        v = f"ERR {e}"
                print("   ", ch.uuid, ch.properties, v)


asyncio.run(main())
