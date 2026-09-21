"""パイプライン共通の設定。

**置き場所の方針**
- 生の音声・文字起こし・詳細要約は「安全領域」に置く。既定は `~/Lifelog`
- 後で暗号化ボリュームに移すときは、環境変数 `LIFELOG_HOME` を変えるだけでよい
- **iCloud と同期するフォルダ（書類・デスクトップ）には置かない**

**ネットへ出さない方針**
- 文字起こしも要約も手元で動く。モデルの取得以外にネットは使わない
- `HF_HUB_OFFLINE=1` を立てて、Whisper がモデルを取りに行かないようにする
"""
import os
import sys
from pathlib import Path

LIFELOG_HOME = Path(os.environ.get("LIFELOG_HOME", Path.home() / "Lifelog"))

# 手元の LLM（Ollama）
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("LIFELOG_OLLAMA_MODEL", "qwen2.5:14b")

# 文字起こし
WHISPER_MODEL = os.environ.get("LIFELOG_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")

SAMPLE_RATE = 16000
PAGE = 440
MARKER_TAG = 0xFF
MARKER_LEN = 16

ICLOUD_HINTS = ("Library/Mobile Documents", "/Documents", "/Desktop")


def day_dir(date: str) -> Path:
    """その日の作業場所。無ければ作る。"""
    d = LIFELOG_HOME / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_placement() -> None:
    """置き場所が危なくないかだけ確かめる（iCloud 配下を避ける）。"""
    p = str(LIFELOG_HOME.resolve())
    for hint in ICLOUD_HINTS:
        if hint in p:
            print(f"⚠ 置き場所が iCloud と同期する場所かもしれません: {p}", file=sys.stderr)
            print("  LIFELOG_HOME を別の場所にしてください", file=sys.stderr)
            break


def force_offline() -> None:
    """モデルを取りに行かせない（取得済み前提で動かす）。"""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
