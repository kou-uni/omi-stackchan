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
#
# **2号機（計算用に借りている機械）は、いつでも切れるようにしておく。**
#   - 毎日の流れ（吸い出し→文字起こし→要約→関所）は **1号機だけで完結する**
#   - 重い実験（大きい教師モデル・学習・大量評価）だけ、あれば2号機を使う
#   - 2号機が見えなければ、黙って1号機に落ちる。**止まらない**
#   - 2号機には**個人データを置かない**（返すときに消すものが無い状態にする）
LOCAL_OLLAMA = "http://127.0.0.1:11434"
REMOTE_OLLAMA = os.environ.get("OLLAMA_REMOTE", "")  # 例: http://169.254.10.2:11434


def _alive(url: str, timeout: float = 1.5) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def ollama_host(*, prefer_remote: bool = False) -> str:
    """使う Ollama を決める。2号機を優先する指定でも、居なければ1号機に落ちる。"""
    if prefer_remote and REMOTE_OLLAMA and _alive(REMOTE_OLLAMA):
        return REMOTE_OLLAMA.rstrip("/")
    return os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA).rstrip("/")


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA).rstrip("/")
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
