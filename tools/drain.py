"""本体に貯まった音声を BLE で吸い出す（fw 3.0.15 の旧プロトコル）。中身は解釈せず生バイトで保存する。

使い方:
  python tools/drain.py OUT.bin           # 途中まであれば続きから（440バイト境界に切り下げて再開）
  python tools/drain.py OUT.bin --delete  # 吸い出し完了＝サイズ一致を確かめてから本体のファイルを削除

プロトコル（storage.c @ Omi_CV1_v3.0.15）:
  制御 30295781 に [cmd, file_num=1, offset(BE32)] を書く。notify も同じ特性に来る
  cmd: 0=READ 1=DELETE 2=NUKE 3=STOP 50=HEARTBEAT
  notify: 1バイト = 結果（0=受理 / 100=転送完了 / 200=削除完了 / その他=エラー）、それ以外 = データ（最大440バイト）
  状態 30295782 = [file_size, offset]（uint32 LE）

出力先はリポジトリの外に置くこと。音声はコミットしない。
"""
import asyncio
import hashlib
import os
import struct
import sys
import time

from bleak import BleakClient

from common import STORAGE_CONTROL, STORAGE_STATUS, find_omi

CHUNK = 440
READ, DELETE, STOP, HEARTBEAT = 0, 1, 3, 50

out = sys.argv[1]
do_delete = "--delete" in sys.argv


def cmd(c: int, offset: int | None = None) -> bytes:
    return bytes([c, 1]) + (struct.pack(">I", offset) if offset is not None else b"")


async def read_status(c: BleakClient) -> tuple[int, int]:
    raw = bytes(await c.read_gatt_char(STORAGE_STATUS))
    return struct.unpack("<2I", raw[:8])


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


async def drain_once(addr: str, file_size: int) -> str:
    have = os.path.getsize(out) if os.path.exists(out) else 0
    start = have - have % CHUNK
    if start >= file_size:
        return "complete"
    f = open(out, "r+b" if have else "wb")
    f.seek(start)
    f.truncate()
    pos = {"n": start, "t0": time.monotonic(), "last": time.monotonic()}
    done = asyncio.Event()
    result = {"code": None}

    def on_notify(_, data: bytearray):
        if len(data) == 1:
            result["code"] = data[0]
            if data[0] != 0:
                done.set()
            return
        f.write(data)
        pos["n"] += len(data)
        now = time.monotonic()
        if now - pos["last"] > 10:
            pos["last"] = now
            rate = (pos["n"] - start) / (now - pos["t0"]) / 1024
            left = (file_size - pos["n"]) / 1024 / max(rate, 0.01) / 60
            print(f"  {pos['n'] / 1e6:7.1f}/{file_size / 1e6:.1f}MB  {rate:5.1f}KB/s  残り約{left:.0f}分", flush=True)
        if pos["n"] >= file_size:
            done.set()

    gone = asyncio.Event()
    try:
        async with BleakClient(addr, timeout=30, disconnected_callback=lambda _: gone.set()) as c:
            print(f"connected mtu={c.mtu_size} start={start}", flush=True)
            await c.start_notify(STORAGE_CONTROL, on_notify)
            await c.write_gatt_char(STORAGE_CONTROL, cmd(READ, start), response=True)
            # HEARTBEAT は無くても転送は止まらない（100パケットごとに offset を保存するだけ）。
            # 書き込み1回ごとにファーム側が500ms寝るので、間隔は長めにとる
            tick = 0
            while not done.is_set() and not gone.is_set():
                await asyncio.sleep(1)
                tick += 1
                if c.is_connected and tick % 15 == 0:
                    await c.write_gatt_char(STORAGE_CONTROL, cmd(HEARTBEAT), response=True)
            if c.is_connected and not done.is_set():
                await c.write_gatt_char(STORAGE_CONTROL, cmd(STOP), response=True)
    finally:
        f.close()
    if pos["n"] >= file_size:
        return "complete"
    return f"interrupted at {pos['n']} (code={result['code']}, disconnected={gone.is_set()})"


async def main():
    addr = await find_omi()
    # 電波が弱いとサービス探索中に切れる（2026-09-19 に3回）。繋がるまで繰り返す
    for attempt in range(1, 11):
        try:
            async with BleakClient(addr, timeout=30) as c:
                file_size, offset = await read_status(c)
            break
        except Exception as e:  # noqa: BLE001
            print(f"status attempt {attempt}: {e}", flush=True)
            await asyncio.sleep(3)
    else:
        sys.exit("Omi に繋がらない。Mac のすぐ横に置く")
    print(f"device file_size={file_size} saved_offset={offset}", flush=True)

    for attempt in range(1, 200):
        try:
            state = await drain_once(addr, file_size)
        except Exception as e:  # noqa: BLE001
            state = f"error: {e}"
        print(f"attempt {attempt}: {state}", flush=True)
        if state == "complete":
            break
        await asyncio.sleep(3)
        addr = await find_omi()

    got = os.path.getsize(out)
    if got != file_size:
        print(f"NOT COMPLETE: got={got} expected={file_size}. 削除しない")
        sys.exit(1)
    digest = sha256(out)
    with open(out + ".sha256", "w") as h:
        h.write(f"{digest}  {os.path.basename(out)}\n")
    print(f"OK size={got} sha256={digest}")

    if not do_delete:
        return
    async with BleakClient(addr, timeout=30) as c:
        codes = []
        await c.start_notify(STORAGE_CONTROL, lambda _, d: codes.append(d[0]) if len(d) == 1 else None)
        await c.write_gatt_char(STORAGE_CONTROL, cmd(DELETE), response=True)
        for _ in range(30):
            if 200 in codes:
                break
            await asyncio.sleep(1)
        after = await read_status(c)
    print(f"delete notify={codes} status_after={after}")


asyncio.run(main())
