#!/usr/bin/env python3
"""Run the font evaluations against the skill in this repository and print the results.

    python3 -I tools/evals/fonts/run_checks.py WORK_DIR [--json RESULTS.json]

WORK_DIR must be an empty folder or a folder that this script made before. The script
makes the fixtures (make_fixtures.py), then runs each scenario of scenarios.json. Every
command of the skill runs:
  - in a new network namespace (`unshare -rn`) when the machine allows it, so no process
    can reach the network;
  - under strace (when installed), which logs every connect() and sendto() of every
    process, LibreOffice included; an AF_INET or AF_INET6 call is a failure;
  - for Python scripts, under audit_run.py, which logs every Python network event.
A scenario passes when all of its checks pass. The exit code is 0 only when all pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
SKILL = REPO / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
SCRIPTS = SKILL / "scripts"
INET = re.compile(r"AF_INET6?\b")
#: fontconfig's cache folders outside any work folder: the system one and the user's
CACHE_DIRS = (Path("/var/cache/fontconfig"), Path.home() / ".cache" / "fontconfig", Path.home() / ".fontconfig")


def cache_listing() -> dict[str, tuple[int, int]]:
    """Every file in fontconfig's cache folders, with its size and modification time."""
    out = {}
    for folder in CACHE_DIRS:
        if folder.is_dir():
            for f in folder.iterdir():
                st = f.stat()
                out[str(f)] = (st.st_size, st.st_mtime_ns)
    return out


class Runner:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.logs = work / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.unshare = shutil.which("unshare") is not None and subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode == 0
        self.strace = shutil.which("strace") is not None
        self.count = 0
        self.caches_before = cache_listing()

    def run(self, script: str, *args: str, fonts: Path | None = None) -> subprocess.CompletedProcess:
        """One skill script, with DECK_FONTS set to `fonts` (unset when None)."""
        self.count += 1
        env = {k: v for k, v in os.environ.items() if k != "DECK_FONTS"}
        env["DECK_WORK"] = str(self.work)
        if fonts is not None:
            env["DECK_FONTS"] = str(fonts)
        audit = self.logs / f"{self.count:03d}.audit"
        cmd = [sys.executable, "-I", str(HERE / "audit_run.py"), str(audit), str(SCRIPTS / script), *args]
        if self.strace:
            cmd = ["strace", "-f", "-qq", "-e", "trace=connect,sendto", "-o", str(self.logs / f"{self.count:03d}.strace"), *cmd]
        if self.unshare:
            cmd = ["unshare", "-rn", *cmd]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, env=env, cwd=SKILL)
        (self.logs / f"{self.count:03d}.cmd").write_text(" ".join(cmd) + f"\nexit {done.returncode}\n--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}")
        return done

    def network_attempts(self) -> list[str]:
        found = []
        for log in sorted(self.logs.glob("*.audit")):
            found += [f"{log.name}: {line}" for line in log.read_text().splitlines()]
        for log in sorted(self.logs.glob("*.strace")):
            found += [f"{log.name}: {line}" for line in log.read_text().splitlines() if INET.search(line)]
        return found


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def face(report: dict, name: str) -> dict:
    return next((f for f in report.get("faces", []) if f.get("face") == name), {})


def pdf_faces(pdf: Path) -> str:
    return subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, timeout=60).stdout if pdf.exists() else ""


def system_fc_match(name: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in ("FONTCONFIG_FILE", "DECK_FONTS")}
    return subprocess.run(["fc-match", "-f", "%{family}", name], capture_output=True, text=True, timeout=30, env=env).stdout


def scenarios(r: Runner, fix: Path) -> dict[str, list[tuple[str, bool, str]]]:
    out: dict[str, list[tuple[str, bool, str]]] = {}
    w = r.work

    # S1: every face of the reference is installed (or has an installed metric-compatible clone)
    folder = w / "s1" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    rep = w / "s1" / "fonts.json"
    p = r.run("fonts.py", "report", str(fix / "deck-installed.pptx"), "-o", str(rep), fonts=folder)
    j = load(rep)
    out["S1 installed faces"] = [
        ("report exits 0", p.returncode == 0, f"exit {p.returncode}: {p.stderr.strip()[-300:]}"),
        ("each text face resolves on this machine", bool(j.get("faces")) and all(f.get("status") in ("installed", "metric_compatible") for f in j["faces"] if f.get("used_for") == "text"),
         str([(f.get("face"), f.get("status")) for f in j.get("faces", [])])),
        ("no stand-in is proposed", all(not f.get("stand_in") for f in j.get("faces", [])), ""),
    ]

    # S2: an embedded font whose fsType allows embedding
    folder = w / "s2" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    rep = w / "s2" / "fonts.json"
    ref = fix / "deck-embedded-ok.pptx"
    p1 = r.run("fonts.py", "report", str(ref), "-o", str(rep), fonts=folder)
    j1 = load(rep)
    f1 = face(j1, "Evalprobe Serif")
    p2 = r.run("fonts.py", "extract", str(ref), fonts=folder)
    after_refusal = sorted(x.name for x in folder.iterdir())
    p3 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    extracted = sorted(x.name for x in folder.iterdir() if x.suffix.lower() in (".ttf", ".otf"))
    p4 = r.run("fonts.py", "report", str(ref), "-o", str(w / "s2" / "fonts-after.json"), fonts=folder)
    f4 = face(load(w / "s2" / "fonts-after.json"), "Evalprobe Serif")
    p5 = r.run("render.py", str(ref), "--out", str(w / "s2" / "renders"), "--keep-pdf", str(w / "s2" / "render.pdf"), fonts=folder)
    out["S2 embedded font, embedding allowed"] = [
        ("report exits 3 (the user must act)", p1.returncode == 3, f"exit {p1.returncode}: {p1.stderr.strip()[-300:]}"),
        ("the face reads embedded and extractable, permission installable", f1.get("status") == "embedded_extractable" and f1.get("permission") == "installable", str(f1)),
        ("extract without --licence-confirmed refuses and writes no font", p2.returncode != 0 and not [n for n in after_refusal if n.endswith((".ttf", ".otf"))], f"exit {p2.returncode}, folder {after_refusal}"),
        ("extract with --licence-confirmed writes the font into the fonts folder", p3.returncode == 0 and len(extracted) == 1, f"exit {p3.returncode}, {extracted}, {p3.stderr.strip()[-300:]}"),
        ("the confirmation is recorded with the user's words", "the user said they hold a licence" in (folder / "licence-confirmations.json").read_text() if (folder / "licence-confirmations.json").exists() else False, ""),
        ("the report then resolves the face from the fonts folder and exits 0", p4.returncode == 0 and f4.get("status") == "work_folder", str(f4)),
        ("LibreOffice draws the face from the fonts folder", p5.returncode == 0 and "EvalprobeSerif" in pdf_faces(w / "s2" / "render.pdf"), pdf_faces(w / "s2" / "render.pdf")),
        ("nothing changed system-wide: fontconfig without the run's config does not know the face", "Evalprobe" not in system_fc_match("Evalprobe Serif"), system_fc_match("Evalprobe Serif")),
    ]

    # S3: an embedded font whose fsType is restricted
    folder = w / "s3" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    rep = w / "s3" / "fonts.json"
    ref = fix / "deck-embedded-restricted.pptx"
    p1 = r.run("fonts.py", "report", str(ref), "-o", str(rep), fonts=folder)
    f1 = face(load(rep), "Evalprobe Locked")
    p2 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    files = sorted(x.name for x in folder.iterdir() if x.suffix.lower() in (".ttf", ".otf"))
    locked_folder = w / "s3" / "fonts-with-locked-file"
    locked_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(fix / "fontsrc" / "EvalprobeLocked-Regular.ttf", locked_folder / "EvalprobeLocked-Regular.ttf")
    p3 = r.run("fonts.py", "report", str(ref), "-o", str(w / "s3" / "fonts-locked-file.json"), fonts=locked_folder)
    j3 = load(w / "s3" / "fonts-locked-file.json")
    out["S3 embedded font, restricted"] = [
        ("report exits 3", p1.returncode == 3, f"exit {p1.returncode}"),
        ("the face reads missing, because the embedded copy is restricted", f1.get("status") == "missing" and f1.get("permission") == "restricted", str(f1)),
        ("a stand-in is proposed: fc-match's face, marked not metric-compatible", bool(f1.get("stand_in")) and f1["stand_in"].get("metric_compatible") is False, str(f1.get("stand_in"))),
        ("the width difference says it cannot be measured", (f1.get("width_difference") or {}).get("measurable") is False, str(f1.get("width_difference"))),
        ("the report tells the user what to supply and where", str(folder) in json.dumps(f1.get("user_can_supply", "")), str(f1.get("user_can_supply"))),
        ("extract, even with the confirmation, writes nothing and says restricted", p2.returncode != 0 and not files and "restricted" in (p2.stdout + p2.stderr), f"exit {p2.returncode}, {files}"),
        ("a restricted file the user puts in the fonts folder is not used, and the report says why",
         p3.returncode == 3 and face(j3, "Evalprobe Locked").get("status") == "missing"
         and any("restricted" in x.get("why", "") for x in j3.get("fonts_folder_files_not_used", [])), str(j3.get("fonts_folder_files_not_used"))),
    ]

    # S4: a PDF whose only copy of the face is an embedded subset
    folder = w / "s4" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    rep = w / "s4" / "fonts.json"
    p1 = r.run("fonts.py", "report", str(fix / "subset.pdf"), "-o", str(rep), fonts=folder)
    f1 = face(load(rep), "Evalprobe Serif")
    wd = f1.get("width_difference") or {}
    # once the guide exists, only the faces it sets count: this guide sets Inter, the stock no-reference example's face
    draft, guide = w / "s4" / "draft.json", w / "s4" / "guide.json"
    r.run("extract_style.py", "--blank", "-o", str(draft))
    r.run("complete_guide.py", str(draft), str(SKILL / "examples" / "no-reference.completion.json"), "-o", str(guide))
    p2 = r.run("fonts.py", "report", str(fix / "subset.pdf"), "--guide", str(guide), "-o", str(w / "s4" / "with-guide.json"), fonts=folder)
    f2 = face(load(w / "s4" / "with-guide.json"), "Evalprobe Serif")
    out["S4 PDF with a subset font only"] = [
        ("report exits 3", p1.returncode == 3, f"exit {p1.returncode}: {p1.stderr.strip()[-300:]}"),
        ("the face reads missing, as a PDF subset", f1.get("status") == "missing" and f1.get("source") == "pdf_subset", str(f1)),
        ("a stand-in is proposed", bool(f1.get("stand_in")), str(f1.get("stand_in"))),
        ("the stand-in's width is measured against the reference's own text", wd.get("measurable") is True and isinstance(wd.get("percent"), (int, float)) and wd.get("runs", 0) > 0, str(wd)),
        ("with a guide that does not set the face, it is listed as reference only and the report exits 0",
         p2.returncode == 0 and f2.get("in_guide") is False, f"exit {p2.returncode}, {f2.get('in_guide')}"),
    ]

    # S5: the user supplies the font files in the fonts folder
    folder = w / "s5" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(fix / "fontsrc" / "EvalprobeSerif-Regular.ttf", folder / "EvalprobeSerif-Regular.ttf")
    rep = w / "s5" / "fonts.json"
    p1 = r.run("fonts.py", "report", str(fix / "deck-named.pptx"), "-o", str(rep), fonts=folder)
    f1 = face(load(rep), "Evalprobe Serif")
    p2 = r.run("render.py", str(fix / "deck-named.pptx"), "--out", str(w / "s5" / "renders"), "--keep-pdf", str(w / "s5" / "render.pdf"), fonts=folder)
    p3 = r.run("fonts.py", "report", str(fix / "deck-named.pptx"), "-o", str(w / "s5" / "fonts-unset.json"), fonts=None)
    out["S5 the user supplies the font"] = [
        ("report exits 0", p1.returncode == 0, f"exit {p1.returncode}: {p1.stderr.strip()[-300:]}"),
        ("the face resolves from the user's file in the fonts folder", f1.get("status") == "work_folder" and f1.get("file") == str(folder / "EvalprobeSerif-Regular.ttf"), str(f1)),
        ("the text ruler measures with that file", f1.get("measured_with", {}).get("file") == str(folder / "EvalprobeSerif-Regular.ttf"), str(f1.get("measured_with"))),
        ("LibreOffice draws the face from that file", p2.returncode == 0 and "EvalprobeSerif" in pdf_faces(w / "s5" / "render.pdf"), pdf_faces(w / "s5" / "render.pdf")),
        ("with DECK_FONTS unset, the report refuses by name", p3.returncode not in (0, 3) and "DECK_FONTS" in (p3.stdout + p3.stderr), f"exit {p3.returncode}: {(p3.stdout + p3.stderr).strip()[-300:]}"),
    ]

    # S6: no reference; the guide names a face that a recipient may lack
    folder = w / "s6" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    draft, guide = w / "s6" / "draft.json", w / "s6" / "guide.json"
    completion = json.loads((SKILL / "examples" / "no-reference.completion.json").read_text())
    completion["/typography/families"] = {"major": "Evalprobe Serif", "minor": "Evalprobe Serif"}
    (w / "s6" / "completion.json").write_text(json.dumps(completion))
    r.run("extract_style.py", "--blank", "-o", str(draft))
    pc = r.run("complete_guide.py", str(draft), str(w / "s6" / "completion.json"), "-o", str(guide))
    p1 = r.run("fonts.py", "report", "--guide", str(guide), "-o", str(w / "s6" / "missing.json"), fonts=folder)
    j1 = load(w / "s6" / "missing.json")
    shutil.copy(fix / "fontsrc" / "EvalprobeSerif-Regular.ttf", folder / "EvalprobeSerif-Regular.ttf")
    p15 = r.run("fonts.py", "report", "--guide", str(guide), "-o", str(w / "s6" / "regular-only.json"), fonts=folder)
    f15 = face(load(w / "s6" / "regular-only.json"), "Evalprobe Serif")
    shutil.copy(fix / "fontsrc" / "EvalprobeSerif-Bold.ttf", folder / "EvalprobeSerif-Bold.ttf")
    p2 = r.run("fonts.py", "report", "--guide", str(guide), "-o", str(w / "s6" / "supplied.json"), fonts=folder)
    j2 = load(w / "s6" / "supplied.json")
    out["S6 no reference, a face the recipient may lack"] = [
        ("the guide completes", pc.returncode == 0, pc.stderr.strip()[-300:]),
        ("with no file, the report exits 3 and reads the face missing", p1.returncode == 3 and face(j1, "Evalprobe Serif").get("status") == "missing", f"exit {p1.returncode}"),
        ("with the regular file only, the report exits 3 and names the bold style the guide's titles need", p15.returncode == 3 and f15.get("styles_missing") == ["bold"], str(f15.get("styles_missing"))),
        ("with the user's regular and bold files, the report exits 0", p2.returncode == 0, f"exit {p2.returncode}: {p2.stderr.strip()[-300:]}"),
        ("the report says the recipient needs the face, because the deck embeds no font", any("Evalprobe Serif" in line for line in j2.get("recipient", [])), str(j2.get("recipient"))),
    ]

    # S7: no command made a network call, and nothing outside the work folder changed
    attempts = r.network_attempts()
    caches_after = cache_listing()
    out["S7 no network use; nothing changed outside the work folder"] = [
        ("every command ran in a network namespace with no network", r.unshare, "unshare -rn available" if r.unshare else "unshare -rn is not available here: only the logs below apply"),
        ("every process was traced for connect() and sendto()", r.strace, "strace available" if r.strace else "strace is not installed"),
        ("no Python network event and no AF_INET or AF_INET6 call", not attempts, "\n".join(attempts[:20])),
        ("no fontconfig cache file was added or changed outside the work folder", caches_after == r.caches_before,
         str(sorted(set(caches_after.items()) ^ set(r.caches_before.items()))[:400])),
    ]
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    work = Path(args.work).resolve()
    if work.exists() and any(work.iterdir()) and not (work / "logs").exists():
        sys.exit(f"{work} is not empty and was not made by this script")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    fix = work / "fixtures"
    subprocess.run([sys.executable, "-I", str(HERE / "make_fixtures.py"), str(fix)], check=True, capture_output=True, timeout=900)
    runner = Runner(work)
    results = scenarios(runner, fix)
    passed = 0
    for name, checks in results.items():
        ok = all(c[1] for c in checks)
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        for label, good, detail in checks:
            print(f"   {'ok  ' if good else 'FAIL'} {label}" + ("" if good or not detail else f"\n        {detail[:400]}"))
    print(f"{passed} of {len(results)} scenarios pass; commands logged in {runner.logs}")
    if args.json:
        Path(args.json).write_text(json.dumps({k: [{"check": c[0], "pass": c[1], "detail": c[2]} for c in v] for k, v in results.items()}, indent=1))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
