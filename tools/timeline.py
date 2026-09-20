"""吸い出したファイルから「時刻の印」だけを拾って、録音の区切りを表にする。

**音声の中身は読まない。** 印（メタ情報）だけを見る。

使い方: python tools/timeline.py ~/omi-export/omi-cv1-YYYYMMDD.bin

保存の形（自前ファーム）:
  440バイトのページに [長さ][中身] を詰める。長さ 0 = そのページはそこまで
  長さ 0xFF = 時刻の印。中身は 'T','S',版,同期済み,起動ID(4),起動からの経過ms(4),epoch秒(4)
"""
import datetime
import struct
import sys

PAGE = 440
MARKER_TAG = 0xFF
MARKER_LEN = 16


def markers(path: str):
    with open(path, "rb") as f:
        page_index = 0
        while chunk := f.read(PAGE):
            pos = 0
            while pos < len(chunk):
                tag = chunk[pos]
                if tag == 0:
                    break
                if tag == MARKER_TAG and chunk[pos + 1 : pos + 3] == b"TS":
                    ver, synced = chunk[pos + 3], chunk[pos + 4]
                    boot_id, uptime_ms, epoch_s = struct.unpack("<III", chunk[pos + 5 : pos + 17])
                    yield page_index * PAGE + pos, ver, synced, boot_id, uptime_ms, epoch_s
                    pos += 1 + MARKER_LEN
                else:
                    pos += 1 + tag
            page_index += 1


def main():
    path = sys.argv[1]
    prev_boot = None
    count = 0
    for off, ver, synced, boot_id, uptime_ms, epoch_s in markers(path):
        count += 1
        when = datetime.datetime.fromtimestamp(epoch_s).strftime("%Y-%m-%d %H:%M:%S") if synced else "時刻なし"
        note = ""
        if prev_boot is not None and boot_id != prev_boot:
            note = "  ← ここで電源が入り直している"
        prev_boot = boot_id
        print(f"{off:>12,}  {when}  起動ID {boot_id:#010x}  経過 {uptime_ms / 1000:8.1f}秒{note}")
    if count == 0:
        print("印が1つも無い。純正ファームで録ったもの（時刻は入っていない）")


main()
