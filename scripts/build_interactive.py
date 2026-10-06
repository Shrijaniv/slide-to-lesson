#!/usr/bin/env python3
"""Wrap a narrated lecture MP4 in a local player with timed concept checks."""
import argparse
import html
import json
from pathlib import Path


def build(video: Path, timings_file: Path, quizzes_file: Path, output: Path):
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise ValueError("Video must be an existing MP4")
    if output.parent.resolve() != video.parent.resolve():
        raise ValueError("HTML output must be beside the MP4 so the local player can find it")
    timings = json.loads(timings_file.read_text(encoding="utf-8"))
    quizzes = json.loads(quizzes_file.read_text(encoding="utf-8"))
    if not isinstance(timings, list) or not timings or not isinstance(quizzes, list) or not quizzes:
        raise ValueError("Timings and quizzes must be nonempty JSON arrays")
    ends = {}
    for i, item in enumerate(timings, 1):
        if not isinstance(item, dict) or item.get("slide") != i:
            raise ValueError("Timings must list slides in order, starting at 1")
        ends[i] = float(item["end_seconds"])
        if ends[i] <= 0 or (i > 1 and ends[i] <= ends[i - 1]):
            raise ValueError("Slide end times must increase")
    seen = set()
    checks = []
    for item in quizzes:
        if not isinstance(item, dict):
            raise ValueError("Each quiz must be an object")
        slide = item.get("after_slide")
        if type(slide) is not int or not 1 <= slide < len(timings) or slide in seen:
            raise ValueError("Each quiz needs a unique after_slide before the final slide")
        seen.add(slide)
        options = item.get("options")
        correct = item.get("correct_index")
        if (not isinstance(item.get("question"), str) or not item["question"].strip()
                or not isinstance(item.get("explanation"), str) or not item["explanation"].strip()
                or not isinstance(options, list) or not 2 <= len(options) <= 4
                or not all(isinstance(x, str) and x.strip() for x in options)
                or type(correct) is not int or not 0 <= correct < len(options)):
            raise ValueError(f"Invalid question, options, answer, or explanation after slide {slide}")
        checks.append({"after_slide": slide, "at": round(max(0, ends[slide] - 0.2), 3),
                       "question": item["question"], "options": options,
                       "correct_index": correct, "explanation": item["explanation"]})
    checks.sort(key=lambda x: x["after_slide"])
    data = json.dumps(checks, ensure_ascii=False).replace("<", "\\u003c")
    source = html.escape(video.name, quote=True)
    title = html.escape(video.stem.replace("-", " ").title())
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — interactive lesson</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui, -apple-system, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #101725; color: #f5f7fc; }}
main {{ max-width: 1120px; margin: auto; padding: 24px; }}
h1 {{ font-size: clamp(1.5rem,3vw,2.2rem); margin: 0 0 8px; }}
.lead {{ color: #bec9db; margin: 0 0 18px; }}
.player {{ position: relative; background: black; border-radius: 14px; overflow: hidden; box-shadow: 0 16px 40px #0008; }}
video {{ display: block; width: 100%; aspect-ratio: 16/9; }}
.quiz {{ position: absolute; inset: 0; background: #0e1729f2; display: grid; place-items: center; padding: 18px; overflow: auto; }}
.quiz[hidden] {{ display: none; }}
.card {{ width: min(100%, 700px); background: #1b2a43; border: 1px solid #607798; border-radius: 18px; padding: clamp(18px,3vw,32px); }}
.eyebrow {{ color: #a6c5ff; font-size: .88rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
h2 {{ font-size: clamp(1.25rem,2.5vw,1.8rem); line-height: 1.25; }}
.options {{ display: grid; gap: 10px; }}
button {{ font: inherit; cursor: pointer; border-radius: 10px; border: 1px solid #8294b1; padding: 11px 15px; background: #263957; color: white; text-align: left; }}
button:hover:not(:disabled), button:focus-visible {{ background: #34517b; outline: 2px solid #b8d4ff; outline-offset: 2px; }}
button:disabled {{ cursor: default; }}
button.correct {{ background: #1b684a; border-color: #63ddaa; }}
button.wrong {{ background: #713942; border-color: #ff9da9; }}
.feedback {{ min-height: 3em; line-height: 1.45; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }}
.actions button {{ background: #ebf2ff; color: #112440; border: none; font-weight: 700; }}
.actions button:hover:not(:disabled) {{ background: #cfe0ff; }}
.note {{ color: #bec9db; margin: 14px 0; }}
</style></head><body><main>
<h1>{title}</h1>
<p class="lead">The video pauses for short concept checks. Choose an answer to see an explanation, then continue.</p>
<div class="player"><video id="lecture" src="{source}" controls preload="metadata" playsinline></video>
<section id="quiz" class="quiz" role="dialog" aria-modal="true" aria-labelledby="question" hidden>
<div class="card"><div id="eyebrow" class="eyebrow"></div><h2 id="question"></h2><div id="options" class="options"></div>
<p id="feedback" class="feedback" aria-live="polite"></p>
<div class="actions"><button id="skip" type="button">Skip check</button><button id="continue" type="button" hidden>Continue lesson</button></div>
</div></section></div>
<p id="progress" class="note"></p><button id="restart" type="button">Restart lesson and checks</button>
</main><script>
const checks = {data};
const video = document.getElementById('lecture');
const quiz = document.getElementById('quiz');
const question = document.getElementById('question');
const options = document.getElementById('options');
const feedback = document.getElementById('feedback');
const continueButton = document.getElementById('continue');
const skipButton = document.getElementById('skip');
const progress = document.getElementById('progress');
const done = new Set();
let active = null;
function updateProgress() {{ progress.textContent = `${{done.size}} of ${{checks.length}} checks answered or skipped`; }}
function showCheck(check) {{
  active = check; video.pause(); video.currentTime = check.at;
  quiz.hidden = false; document.getElementById('eyebrow').textContent = `Check after slide ${{check.after_slide}}`;
  question.textContent = check.question; options.replaceChildren(); feedback.textContent = '';
  continueButton.hidden = true; skipButton.hidden = false;
  check.options.forEach((label, i) => {{
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
    button.addEventListener('click', () => {{
      [...options.children].forEach((choice, j) => {{ choice.disabled = true; if (j === check.correct_index) choice.classList.add('correct'); }});
      if (i !== check.correct_index) button.classList.add('wrong');
      feedback.textContent = (i === check.correct_index ? 'Correct. ' : 'Not quite. ') + check.explanation;
      continueButton.hidden = false; skipButton.hidden = true; continueButton.focus();
    }});
    options.append(button);
  }});
  options.querySelector('button').focus();
}}
function resume() {{
  if (!active) return;
  done.add(active.after_slide); const at = active.at; active = null; quiz.hidden = true;
  updateProgress(); video.currentTime = Math.min(at + 0.25, video.duration || at + 0.25);
  video.play().catch(() => {{ video.focus(); }});
}}
video.addEventListener('timeupdate', () => {{
  if (active) return;
  const next = checks.find(c => !done.has(c.after_slide) && video.currentTime >= c.at);
  if (next) showCheck(next);
}});
video.addEventListener('seeking', () => {{
  if (active) return;
  const next = checks.find(c => !done.has(c.after_slide) && video.currentTime >= c.at);
  if (next) showCheck(next);
}});
continueButton.addEventListener('click', resume); skipButton.addEventListener('click', resume);
document.getElementById('restart').addEventListener('click', () => {{ done.clear(); active = null; quiz.hidden = true; video.pause(); video.currentTime = 0; updateProgress(); video.play().catch(() => {{ video.focus(); }}); }});
updateProgress();
</script></body></html>'''
    output.write_text(page, encoding="utf-8")
    print(f"Interactive lesson: {output}\nChecks: {len(checks)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("timings", type=Path)
    parser.add_argument("quizzes", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        build(args.video.resolve(), args.timings.resolve(), args.quizzes.resolve(), args.output.resolve())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
