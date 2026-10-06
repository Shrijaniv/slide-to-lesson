# Slide to Lesson

A Codex skill for turning PDF lecture slides into a lesson that **teaches the concepts**. It guides slide analysis and detailed narration, then assembles a video from the original slides. Add explanatory animations where motion clarifies a mechanism and optional concept checks that pause a local HTML player between sections.

## Install

Clone this repository, then copy the repository folder to your Codex skills directory as `slide-to-lesson` (for example, `~/.codex/skills/slide-to-lesson`). Start a new Codex chat to make the skill available.

## Requirements

- macOS with Swift and PDFKit for rendering PDF slides
- FFmpeg and FFprobe for video assembly
- Python 3
- The macOS `say` command for the default local voice; an ElevenLabs account is optional

The skill's [SKILL.md](SKILL.md) describes the teaching workflow. The scripts only assemble material; they do not write the lesson, generate animations, or verify the academic content.

## Build a video

Have Codex write a UTF-8 `narration.json` array with one nonempty string per PDF slide. The command below generates speech with a local macOS voice and assembles the lesson. You do not need to record or prepare audio clips:

```bash
python3 scripts/build_video.py slides.pdf narration.json lesson.mp4
```

For an ElevenLabs voice, set `ELEVENLABS_API_KEY` in your shell and select `--tts elevenlabs`. The default voice is George; pass `--voice-id` to choose another voice. The script sends the narration text to ElevenLabs and uses your account's quota. Keep the key out of files and chat messages.

```bash
export ELEVENLABS_API_KEY='your-key'
python3 scripts/build_video.py slides.pdf narration.json lesson.mp4 --tts elevenlabs
```

If you already have audio from another source, `--audio-dir` accepts one file per slide named `slide-01.mp3`, `slide-02.mp3`, and so on (also WAV, M4A, AIFF). To replace selected still slides with silent explanatory animations, supply clips named `slide-01.mp4`, and so on:

```bash
python3 scripts/build_video.py slides.pdf narration.json lesson.mp4 \
  --audio-dir audio --visual-dir visuals
```

The builder writes `lesson.mp4`, `lesson-transcript.txt`, and `lesson-timings.json`. The MP4 includes slide chapters. Animations are trimmed to the narration segment or held on their final frame.

## Add concept checks

Write `quizzes.json` as an array of checks. For example:

```json
[
  {
    "after_slide": 3,
    "question": "Which change would increase the rate in this model?",
    "options": ["Increase the input", "Decrease the input"],
    "correct_index": 0,
    "explanation": "The output responds directly to the input in the model just shown."
  }
]
```

Build the local player next to the MP4:

```bash
python3 scripts/build_interactive.py lesson.mp4 lesson-timings.json quizzes.json lesson.html
```

Open `lesson.html` in a browser. The player pauses for each check, explains the answer, and lets the learner skip. Keep the HTML and MP4 in the same directory when sharing. The MP4 plays independently without interactive checks.

## Privacy

The local build uses local slides and media. If you choose an external voice or animation provider, review what you send to that provider. Never put API keys in narration files, scripts, or this repository.

## License

MIT. See [LICENSE](LICENSE).
