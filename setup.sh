#!/bin/sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Slide to Lesson currently requires macOS for Swift/PDFKit and the local voice." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to install FFmpeg and Python. Install it from https://brew.sh/ and rerun ./setup.sh." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  brew install python
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  brew install ffmpeg
fi

if ! command -v swift >/dev/null 2>&1; then
  echo "Swift is missing. Install Apple's Command Line Tools with: xcode-select --install" >&2
  exit 1
fi

requirements="$(dirname "$0")/requirements.txt"
if grep -Eq '^[[:space:]]*[^#[:space:]]' "$requirements"; then
  python3 -m pip install -r "$requirements"
fi
echo "Slide to Lesson dependencies are ready."
