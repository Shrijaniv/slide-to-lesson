#!/usr/bin/env python3
"""Build a narrated MP4 from PDF slides and one script per slide."""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def command(args, cache):
    env = dict(os.environ, SWIFT_MODULE_CACHE_PATH=str(cache / "swift"),
               CLANG_MODULE_CACHE_PATH=str(cache / "clang"), XDG_CACHE_HOME=str(cache))
    for name in ("swift", "clang"):
        (cache / name).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(args, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f"Command failed: {args[0]}")[-1200:].strip())
    return result.stdout.strip()


def audio_duration(path, cache):
    value = command(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(path)], cache)
    try:
        seconds = float(value)
    except ValueError as exc:
        raise RuntimeError(f"Audio has no readable duration: {path.name}") from exc
    if not math.isfinite(seconds) or seconds < 0.1:
        raise RuntimeError(f"Audio is empty or too short: {path.name}")
    return seconds


def slide_audio(folder, index):
    matches = [folder / f"slide-{index:02d}{ext}" for ext in (".mp3", ".wav", ".m4a", ".aiff")]
    found = [path for path in matches if path.is_file()]
    if len(found) != 1:
        raise ValueError(f"Expected one audio file for slide {index}: slide-{index:02d}.mp3/.wav/.m4a/.aiff")
    return found[0]


def slide_visual(folder, index):
    if not folder:
        return None
    visual = folder / f"slide-{index:02d}.mp4"
    return visual if visual.is_file() else None


def elevenlabs_audio(script, path, voice_id, model):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ValueError("ELEVENLABS_API_KEY is not set. Export it in your shell before using --tts elevenlabs.")
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        data=json.dumps({"text": script, "model_id": model}).encode("utf-8"),
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ElevenLabs request failed (HTTP {exc.code}). Check your API key, voice, model, and account quota.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach ElevenLabs: {exc.reason}") from exc
    if not audio:
        raise RuntimeError("ElevenLabs returned empty audio.")
    path.write_bytes(audio)


def make_video(pdf, scripts, output, voice, audio_dir=None, visual_dir=None,
               tts="local", voice_id="JBFqnCBsd6RMkjVDRZzb", model="eleven_multilingual_v2"):
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ValueError("Input must be an existing PDF slide deck.")
    if audio_dir and tts != "local":
        raise ValueError("Choose either --audio-dir or --tts elevenlabs.")
    if tts == "elevenlabs" and not os.environ.get("ELEVENLABS_API_KEY", "").strip():
        raise ValueError("ELEVENLABS_API_KEY is not set. Export it in your shell before using --tts elevenlabs.")
    for cmd in (("swift", "ffmpeg", "ffprobe") if audio_dir or tts == "elevenlabs" else ("swift", "say", "ffmpeg", "ffprobe")):
        if not shutil.which(cmd):
            raise RuntimeError(f"Missing required command: {cmd}")
    if audio_dir and not audio_dir.is_dir():
        raise ValueError(f"Audio directory does not exist: {audio_dir}")
    if visual_dir and not visual_dir.is_dir():
        raise ValueError(f"Visual directory does not exist: {visual_dir}")
    narration = json.loads(scripts.read_text(encoding="utf-8"))
    if not isinstance(narration, list) or not narration or not all(isinstance(x, str) and x.strip() for x in narration):
        raise ValueError("Narration must be a JSON array with one nonempty string per slide.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lecture-video-") as temp:
        folder = Path(temp)
        cache = folder / "cache"
        command(["swift", str(HERE / "render.swift"), str(pdf), str(folder)], cache)
        pages = json.loads((folder / "pages.json").read_text())
        if len(pages) != len(narration):
            raise ValueError(f"The PDF has {len(pages)} slides but the script has {len(narration)} entries.")
        segments = []
        timings = []
        start = 0.0
        for index, (page, script) in enumerate(zip(pages, narration), 1):
            print(f"Rendering slide {index}/{len(pages)}", flush=True)
            if audio_dir:
                audio = slide_audio(audio_dir, index)
            elif tts == "elevenlabs":
                audio = folder / f"speech-{index:03}.mp3"
                elevenlabs_audio(script, audio, voice_id, model)
            else:
                speech = folder / f"speech-{index:03}.txt"
                speech.write_text(script, encoding="utf-8")
                audio = folder / f"speech-{index:03}.aiff"
                command(["say", "-v", voice, "-f", str(speech), "-o", str(audio)], cache)
            segment = folder / f"segment-{index:03}.mp4"
            try:
                spoken_seconds = audio_duration(audio, cache)
            except RuntimeError as exc:
                if not audio_dir and tts == "local":
                    raise RuntimeError("The selected Mac voice produced no audio. Try another voice or check macOS speech settings.") from exc
                raise
            seconds = spoken_seconds + 0.35
            visual = slide_visual(visual_dir, index)
            timings.append({"slide": index, "start_seconds": round(start, 3),
                            "speech_seconds": round(spoken_seconds, 3), "end_seconds": round(start + seconds, 3),
                            "visual": "animation" if visual else "slide"})
            start += seconds
            video_input = (["-i", str(visual)] if visual else
                           ["-loop", "1", "-framerate", "24", "-i", str(folder / page["image"])])
            visual_filter = (f"fps=24,tpad=stop_mode=clone:stop_duration={seconds}," if visual else "")
            command(["ffmpeg", "-y", "-loglevel", "error", *video_input,
                     "-i", str(audio), "-t", str(seconds), "-map", "0:v:0", "-map", "1:a:0",
                     "-vf", visual_filter + "scale=1280:720:force_original_aspect_ratio=decrease,"
                            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p",
                     "-c:v", "libx264", "-preset", "veryfast", "-r", "24", "-crf", "22",
                     "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                     "-movflags", "+faststart", str(segment)], cache)
            segments.append(segment)
        concat = folder / "segments.txt"
        concat.write_text("".join(f"file '{str(p)}'\n" for p in segments), encoding="utf-8")
        chapters = folder / "chapters.ffmeta"
        chapters.write_text(";FFMETADATA1\n" + "".join(
            f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(t['start_seconds'] * 1000)}\n"
            f"END={round(t['end_seconds'] * 1000)}\ntitle=Slide {t['slide']}\n" for t in timings), encoding="utf-8")
        command(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                 "-i", str(concat), "-i", str(chapters), "-map_metadata", "1", "-map_chapters", "1",
                 "-c", "copy", "-movflags", "+faststart", str(output)], cache)
    transcript = output.with_name(output.stem + "-transcript.txt")
    transcript.write_text("\n\n".join(f"Slide {i}\n{text}" for i, text in enumerate(narration, 1)) + "\n", encoding="utf-8")
    timing_file = output.with_name(output.stem + "-timings.json")
    timing_file.write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
    print(f"Video: {output}\nTranscript: {transcript}\nSlide timings: {timing_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slides", type=Path)
    parser.add_argument("narration", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--audio-dir", type=Path, help="Use one existing audio file per slide instead of Mac speech")
    parser.add_argument("--visual-dir", type=Path, help="Use optional silent slide-XX.mp4 animations in place of selected slide images")
    parser.add_argument("--tts", choices=("local", "elevenlabs"), default="local", help="Generate narration automatically (default: local macOS voice)")
    parser.add_argument("--voice-id", default="JBFqnCBsd6RMkjVDRZzb", help="ElevenLabs voice ID (default: George)")
    parser.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs model ID")
    args = parser.parse_args()
    try:
        make_video(args.slides.resolve(), args.narration.resolve(), args.output.resolve(),
                   args.voice, args.audio_dir.resolve() if args.audio_dir else None,
                   args.visual_dir.resolve() if args.visual_dir else None,
                   args.tts, args.voice_id, args.model)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
