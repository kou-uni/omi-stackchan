"""Omi に BLE で繋ぐための共通部品。

CoreBluetooth のアドレス（UUID）は Mac ごとに違うので、名前で探す。
"""
import asyncio
import ctypes
import os

from bleak import BleakScanner

AUDIO_SERVICE = "19b10000-e8f2-537e-4f6c-d104768a1214"
AUDIO_DATA = "19b10001-e8f2-537e-4f6c-d104768a1214"
AUDIO_CODEC = "19b10002-e8f2-537e-4f6c-d104768a1214"
STORAGE_SERVICE = "30295780-4301-eabd-2904-2849adfeae43"
STORAGE_CONTROL = "30295781-4301-eabd-2904-2849adfeae43"  # write + notify
STORAGE_STATUS = "30295782-4301-eabd-2904-2849adfeae43"  # read + notify

SAMPLE_RATE = 16000


def load_libopus():
    """Homebrew の libopus を opuslib より先に読ませる（Apple Silicon の既定パスに無いため）。"""
    for p in ("/opt/homebrew/lib/libopus.0.dylib", "/usr/local/lib/libopus.0.dylib"):
        if os.path.exists(p):
            ctypes.CDLL(p)
            return p
    raise RuntimeError("libopus が見つからない。brew install opus")


async def find_omi(timeout: float = 10.0) -> str:
    """名前が Omi で始まる端末のアドレスを返す。環境変数 OMI_ADDRESS があればそれを使う。"""
    if addr := os.environ.get("OMI_ADDRESS"):
        return addr
    devices = await asyncio.wait_for(
        BleakScanner.discover(timeout=timeout, return_adv=True), timeout + 20
    )
    for addr, (dev, adv) in devices.items():
        name = dev.name or adv.local_name or ""
        if name.startswith("Omi"):
            print(f"found {name} rssi={adv.rssi}")
            return addr
    raise RuntimeError("Omi が見つからない。電源・距離・Bluetooth 権限・iPhone アプリの接続を確認")
