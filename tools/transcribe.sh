#!/bin/zsh
# WAV を手元の Whisper で文字起こしする。初回だけモデル本体を HF から落とす（音声は送らない）。
# 使い方: tools/transcribe.sh data/live.wav
set -eu
in=$1
norm=${in:r}.norm.wav
# Omi の録音は小さい（平均 -46dB）ので、先に音量をそろえる
ffmpeg -hide_banner -loglevel error -y -i "$in" -af loudnorm "$norm"
mlx_whisper "$norm" --model mlx-community/whisper-large-v3-turbo --language ja \
  --output-format txt --output-dir "${in:h}"
cat "${norm:r}.txt"
