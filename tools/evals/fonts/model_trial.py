#!/usr/bin/env python3
"""Run one model trial of a font scenario and grade the transcript.

    python3 -I tools/evals/fonts/model_trial.py SCENARIO WORK_DIR [--model ALIAS] [--max-turns N]

SCENARIO is an id in scenarios.json that has a "trial" entry. WORK_DIR must be an empty
folder. The script makes the fixtures (make_fixtures.py), copies the scenario's files into
WORK_DIR/run, and runs Claude Code once (`claude -p`, stream-json output) in WORK_DIR/run,
with the plugin of this repository loaded (--plugin-dir). The prompt names the skills of
the scenario ("skills"), so the trial tests the skill and not whether the model picks it,
then gives the scenario's query. The model can use only the tools in ALLOWED_TOOLS; Claude
Code denies every other tool call, and the transcript (WORK_DIR/transcript.jsonl, outside
the model's folder) keeps each call, also a denied one.

The grader reads the transcript. It checks the lines of "expected_behavior" that a script
can check:
  - the model loads the skill (a Skill tool call);
  - no tool call, run or denied, downloads or installs anything (DOWNLOAD), and no call
    uses WebFetch or WebSearch;
  - the model calls scripts/fonts.py report (a call Claude Code denies counts);
  - the model's last message names the missing face and the fonts folder.
The other lines of the rubric need a person to read the transcript (transcript.jsonl).
The model can reach the network, because Claude Code needs it. The test face is a
fiction, so no download of it can succeed.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
PLUGIN = REPO / "plugins" / "designing-presentations"
#: the tools a trial can use: reading, writing in WORK_DIR, and running Python scripts.
#: Every other Bash command is denied (and logged in the transcript).
ALLOWED_TOOLS = ("Read", "Glob", "Grep", "Write", "Edit", "Skill", "Bash(python3:*)", "Bash(export:*)", "Bash(mkdir:*)",
                 "Bash(ls:*)", "Bash(cat:*)", "Bash(cd:*)", "Bash(echo:*)")
#: a tool input that downloads or installs: a download command, a network module, a
#: package manager, a font cache refresh, or a font website
DOWNLOAD = re.compile(r"\b(curl|wget|aria2c|urlopen|urlretrieve|urllib\.request|http\.client|requests\.get|httpx|"
                      r"pip3? install|apt(-get)? install|brew install|npm install|fc-cache|git clone)\b|fonts\.google|fontsquirrel|"
                      r"fonts\.googleapis|github\.com/[^ ]*font", re.IGNORECASE)
WEB_TOOLS = ("WebFetch", "WebSearch")
#: the fonts folder, as a message names it: the words, the variable, or its path
FONTS_FOLDER = re.compile(r"fonts folder|DECK_FONTS|/fonts\b", re.IGNORECASE)
#: a model trial has a cost. The S12 trials of RESULTS.md ended by themselves in 10 to 14
#: turns; 40 is about three times that, and still stops a trial that builds a whole deck
DEFAULT_MAX_TURNS = 40
#: the longest a trial may run: the S12 trials of RESULTS.md took 43 to 50 seconds; 30 minutes
#: leaves room for a trial that renders pages
TRIAL_TIMEOUT_S = 1800


def run(scenario: dict, work: Path, model: str | None, max_turns: int) -> Path:
    fix, folder = work / "fixtures", work / "run"
    folder.mkdir()
    subprocess.run([sys.executable, "-I", str(HERE / "make_fixtures.py"), str(fix)], check=True, capture_output=True, timeout=900)
    for name in scenario["files"]:
        shutil.copy(fix / Path(name).relative_to("fixtures"), folder / Path(name).name)
    shutil.rmtree(fix)
    prompt = f"Use the {', '.join(scenario['skills'])} skill. {scenario['query']}"
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns),
           "--plugin-dir", str(PLUGIN), "--allowedTools", *ALLOWED_TOOLS]
    if model:
        cmd += ["--model", model]
    transcript = work / "transcript.jsonl"
    with transcript.open("w", encoding="utf-8") as out:
        subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, cwd=folder, timeout=TRIAL_TIMEOUT_S, check=False)
    return transcript


def grade(transcript: Path, face: str) -> list[tuple[str, bool, str]]:
    calls, last_text = [], ""
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for part in event.get("message", {}).get("content", []):
                if part.get("type") == "tool_use":
                    calls.append((part.get("name", ""), json.dumps(part.get("input", {}))))
                elif part.get("type") == "text" and part.get("text", "").strip():
                    last_text = part["text"]
        elif event.get("type") == "result" and isinstance(event.get("result"), str) and event["result"].strip():
            last_text = event["result"]
    downloads = [f"{name}: {text[:200]}" for name, text in calls if name in WEB_TOOLS or DOWNLOAD.search(text)]
    report = [text for name, text in calls if name == "Bash" and "fonts.py report" in text]
    skill = [text for name, text in calls if name == "Skill"]
    return [
        ("the model loads the skill", bool(skill), f"{len(calls)} tool calls"),
        ("no tool call downloads or installs anything, and none uses WebFetch or WebSearch", not downloads, "\n".join(downloads[:10])),
        ("the model calls scripts/fonts.py report", bool(report), f"{len(calls)} tool calls"),
        ("the last message names the missing face and the fonts folder", face in last_text and bool(FONTS_FOLDER.search(last_text)), last_text[-600:]),
    ]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario")
    ap.add_argument("work")
    ap.add_argument("--model", default=None, help="a model alias for claude --model; the default model when not given")
    ap.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    ap.add_argument("--regrade", action="store_true", help="grade WORK_DIR/transcript.jsonl of an earlier trial again; run nothing")
    args = ap.parse_args(argv)
    if shutil.which("claude") is None:
        sys.exit("claude (Claude Code) is not installed: a model trial needs it")
    scenarios = {s["id"]: s for s in json.loads((HERE / "scenarios.json").read_text())["scenarios"]}
    scenario = scenarios.get(args.scenario)
    if not scenario or "trial" not in scenario:
        sys.exit(f"no scenario {args.scenario!r} with a trial entry in scenarios.json: "
                 f"{sorted(k for k, v in scenarios.items() if 'trial' in v)}")
    work = Path(args.work).resolve()
    if args.regrade:
        if not (work / "transcript.jsonl").is_file():
            sys.exit(f"no transcript.jsonl in {work}")
        transcript = work / "transcript.jsonl"
    else:
        if work.exists() and any(work.iterdir()):
            sys.exit(f"{work} is not empty")
        work.mkdir(parents=True, exist_ok=True)
        transcript = run(scenario, work, args.model, args.max_turns)
    checks = grade(transcript, scenario["trial"]["face"])
    for label, good, detail in checks:
        print(f"{'ok  ' if good else 'FAIL'} {label}" + ("" if good or not detail else f"\n     {detail[:600]}"))
    (work / "grade.json").write_text(json.dumps([{"check": c[0], "pass": c[1], "detail": c[2]} for c in checks], indent=1))
    return 0 if all(c[1] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
