#!/usr/bin/env python3
"""Run the font evaluations against the skill in this repository and print the results.

    python3 -I tools/evals/fonts/run_checks.py WORK_DIR [--json RESULTS.json]

WORK_DIR must be an empty folder or a folder that this script made before. The script
makes the fixtures (make_fixtures.py), then runs each scenario of scenarios.json. Every
command of the skill runs:
  - in a new network namespace (`unshare -rn`) when the machine allows it, so no process
    can reach the network;
  - under strace (when installed), which logs every socket call of every process,
    LibreOffice included (trace=network: socket, connect, sendto, sendmsg and the rest);
    any AF_INET or AF_INET6 call is a failure, and so is a connect() to a local socket
    other than the name service cache (nscd) and LibreOffice's own pipes, because a local
    socket can lead to a proxy that reaches the network;
  - for Python scripts, under audit_run.py, which logs every Python network event.
A scenario passes when all of its checks pass. The exit code is 0 only when all pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
SKILL = REPO / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
SCRIPTS = SKILL / "scripts"
INET = re.compile(r"AF_INET6?\b")
#: a connect() to a local (AF_UNIX) socket, with its path; "@" opens an abstract socket name
UNIX_CONNECT = re.compile(r'connect\(\d+, \{sa_family=AF_UNIX, sun_path=(@?)"([^"]*)"')
#: the local sockets a run may reach: glibc's name service cache, and LibreOffice's own
#: single-instance pipes (OSL_PIPE_<uid>_SingleOfficeIPC_<hash>), which lead nowhere else
LOCAL_SOCKETS_ALLOWED = re.compile(r"^(/var/run/nscd/socket|/run/nscd/socket|.*/OSL_PIPE_\d+_SingleOfficeIPC_[0-9a-f]+)$")
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
#: a command or module that downloads, in a script the skill ships
DOWNLOADER = re.compile(r"\b(curl|wget|aria2c|urlopen|urlretrieve|urllib\.request|http\.client|httpx|aiohttp|ftplib|"
                        r"import requests|from requests|import socket|from socket|webbrowser|git clone|fc-cache)\b")
#: a font package of apt (fonts-*, ttf-*) or Homebrew (font-*), in any file the skill ships
FONT_PACKAGE = re.compile(r"(?<![\w/.-])(fonts-[a-z0-9]|ttf-[a-z0-9]|font-[a-z0-9]+(?=[\s`'\"]|$))")
#: a download script named in the skill's text
FETCH_SCRIPT = re.compile(r"\bfetch[-_]?(refs)?\.sh\b")
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
        self.unshare = shutil.which("unshare") is not None and subprocess.run(["unshare", "-rn", "true"], capture_output=True, check=False).returncode == 0
        self.strace = shutil.which("strace") is not None
        self.count = 0
        self.caches_before = cache_listing()
        self.temp_before = temp_font_folders(work)

    def command(self, script: str, args: tuple[str, ...], fonts: Path | None, env: dict[str, str] | None) -> tuple[list[str], dict[str, str]]:
        self.count += 1
        full = {k: v for k, v in os.environ.items() if k != "DECK_FONTS"}
        full["DECK_WORK"] = str(self.work)
        if fonts is not None:
            full["DECK_FONTS"] = str(fonts)
        full.update(env or {})
        audit = self.logs / f"{self.count:03d}.audit"
        cmd = [sys.executable, "-I", str(HERE / "audit_run.py"), str(audit), str(SCRIPTS / script), *args]
        if self.strace:
            cmd = ["strace", "-f", "-qq", "-e", "trace=network", "-o", str(self.logs / f"{self.count:03d}.strace"), *cmd]
        if self.unshare:
            cmd = ["unshare", "-rn", *cmd]
        return cmd, full

    def run(self, script: str, *args: str, fonts: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        """One skill script, with DECK_FONTS set to `fonts` (unset when None) and `env` added."""
        cmd, full = self.command(script, args, fonts, env)
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, check=False, env=full, cwd=SKILL)
        (self.logs / f"{self.count:03d}.cmd").write_text(" ".join(cmd) + f"\nexit {done.returncode}\n--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}")
        return done

    def run_killed(self, script: str, *args: str, fonts: Path, after: Path, wait_s: float, grace_s: float) -> int:
        """Start one skill script, wait until `after` exists (or wait_s seconds) and then
        grace_s more, and stop it with SIGTERM, as a timeout or a closed terminal does.
        Returns its exit code."""
        cmd, full = self.command(script, args, fonts, None)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=full, cwd=SKILL, start_new_session=True)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and not after.exists() and proc.poll() is None:
            time.sleep(0.05)
        time.sleep(grace_s)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
        code = proc.wait(timeout=120)
        (self.logs / f"{self.count:03d}.cmd").write_text(" ".join(cmd) + f"\nstopped with SIGTERM; exit {code}\n")
        return code

    def network_attempts(self) -> list[str]:
        found = []
        for log in sorted(self.logs.glob("*.audit")):
            found += [f"{log.name}: {line}" for line in log.read_text().splitlines()]
        for log in sorted(self.logs.glob("*.strace")):
            for line in log.read_text().splitlines():
                m = UNIX_CONNECT.search(line)
                if INET.search(line) or (m and (m.group(1) or not LOCAL_SOCKETS_ALLOWED.match(m.group(2)))):
                    found.append(f"{log.name}: {line}")
        return found


def temp_font_folders(work: Path) -> set[str]:
    """The entries of the temporary folder that hold a font file, the work folder left out:
    a copy of a user's font left there outlives the run and the work folder."""
    out = set()
    tmp = Path(tempfile.gettempdir())
    for entry in tmp.iterdir():
        if entry == work or work.is_relative_to(entry) or not entry.is_dir() or entry.is_symlink():
            continue
        try:
            if any(f.suffix.lower() in FONT_SUFFIXES for f in entry.rglob("*")):
                out.add(str(entry))
        except OSError:
            continue
    return out


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def font_files(folder: Path) -> list[str]:
    return sorted(x.name for x in folder.iterdir() if x.suffix.lower() in FONT_SUFFIXES) if folder.is_dir() else []


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def face(report: dict, name: str) -> dict:
    return next((f for f in report.get("faces", []) if f.get("face") == name), {})


def pdf_faces(pdf: Path) -> str:
    return subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, timeout=60, check=False).stdout if pdf.exists() else ""


def system_fc_match(name: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in ("FONTCONFIG_FILE", "DECK_FONTS")}
    return subprocess.run(["fc-match", "-f", "%{family}", name], capture_output=True, text=True, timeout=30, check=False, env=env).stdout


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
    # extraction run again keeps the file it wrote; a different file under that name is never overwritten
    target = folder / extracted[0] if extracted else folder / "none"
    before = sha(target)
    p6 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    again = sha(target)
    other = fix / "fontsrc" / "EvalprobeSerif-Bold.ttf"
    if target.is_file():
        shutil.copy(other, target)
    p7 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    out["S2 embedded font, embedding allowed"] += [
        ("extract run again exits 0 and leaves the same file", p6.returncode == 0 and before and again == before, f"exit {p6.returncode}: {(p6.stdout + p6.stderr).strip()[-300:]}"),
        ("extract never overwrites a different file of the same name, and says so", p7.returncode != 0 and sha(target) == sha(other)
         and target.name in (p7.stdout + p7.stderr), f"exit {p7.returncode}: {(p7.stdout + p7.stderr).strip()[-300:]}"),
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
    p4 = r.run("render.py", str(fix / "deck-locked-named.pptx"), "--out", str(w / "s3" / "renders"), "--keep-pdf", str(w / "s3" / "render.pdf"), fonts=locked_folder)
    out["S3 embedded font, restricted"] = [
        ("report exits 3", p1.returncode == 3, f"exit {p1.returncode}"),
        ("the face reads missing, because the embedded copy is restricted", f1.get("status") == "missing" and f1.get("permission") == "restricted", str(f1)),
        ("a stand-in is proposed: fc-match's face, marked not metric-compatible", bool(f1.get("stand_in")) and f1["stand_in"].get("metric_compatible") is False, str(f1.get("stand_in"))),
        ("the width difference says it cannot be measured", (f1.get("width_difference") or {}).get("measurable") is False, str(f1.get("width_difference"))),
        ("the report tells the user what to supply and where", str(folder) in json.dumps(f1.get("user_can_supply", "")), str(f1.get("user_can_supply"))),
        ("extract, even with the confirmation, writes nothing and says restricted", p2.returncode != 0 and not files and "restricted" in (p2.stdout + p2.stderr), f"exit {p2.returncode}, {files}"),
        ("a restricted file the user puts in the fonts folder is theirs to use on this machine: the report resolves it and exits 0",
         p3.returncode == 0 and face(j3, "Evalprobe Locked").get("status") == "work_folder" and not j3.get("fonts_folder_files_not_used"),
         f"exit {p3.returncode}, {face(j3, 'Evalprobe Locked').get('status')}, {j3.get('fonts_folder_files_not_used')}"),
        ("LibreOffice draws the deck in that file", p4.returncode == 0 and "EvalprobeLocked" in pdf_faces(w / "s3" / "render.pdf"), pdf_faces(w / "s3" / "render.pdf")),
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
    # SKILL.md exports DECK_FONTS before any script makes the folder: steps 0 and 1 must run
    unmade = w / "s5" / "not-made-yet" / "fonts"
    p4 = r.run("preflight.py", "--reference", str(fix / "deck-installed.pptx"), fonts=unmade)
    p5 = r.run("render.py", str(fix / "deck-installed.pptx"), "--out", str(w / "s5" / "renders-unmade"), fonts=unmade)
    # the copies of the user's files: in the work folder, at the same paths every run, even after a run is stopped
    p6 = r.run("render.py", str(fix / "deck-named.pptx"), "--out", str(w / "s5" / "renders-again"), fonts=folder)
    first = (load(w / "s5" / "renders" / "fonts.json").get("Evalprobe Serif") or {}).get("file", "")
    second = (load(w / "s5" / "renders-again" / "fonts.json").get("Evalprobe Serif") or {}).get("file", "")
    stopped = w / "s5" / "stopped"
    code = r.run_killed("render.py", str(fix / "deck-named.pptx"), "--out", str(stopped), fonts=folder, after=stopped / "fonts.json", wait_s=60, grace_s=0)
    # render.py writes fonts.json once it has read the fonts folder, before LibreOffice runs: it is stopped in between
    stopped_ok = code != 0  # stopped while it ran, not after it finished
    left = sorted(temp_font_folders(w) - r.temp_before)
    out["S5 the user supplies the font"] += [
        ("with DECK_FONTS naming a folder not made yet, preflight and render run", p4.returncode in (0, 1) and "DECK_FONTS" not in (p4.stdout + p4.stderr)
         and p5.returncode == 0, f"preflight exit {p4.returncode}, render exit {p5.returncode}: {(p4.stdout + p4.stderr + p5.stderr).strip()[-300:]}"),
        ("the font file the renders record lies in the work folder, and is the same in two runs",
         p6.returncode == 0 and bool(first) and first == second and Path(first).is_relative_to(w), f"{first} / {second}"),
        ("a run stopped with SIGTERM while it ran leaves no copy of a user's font outside the work folder", stopped_ok and not left, f"exit {code}; {left}"),
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
    # a title at weight 600, which the build sets in the face weight_faces names
    semi = json.loads(json.dumps(completion))
    semi["/typography/families"] = {"major": "Evalprobe Serif", "minor": "Evalprobe Serif", "weight_faces": {"major:600": "Evalprobe Semibold"}}
    semi["/typography/roles/type.title"] = {**semi["/typography/roles/type.title"], "weight": 600}
    (w / "s6" / "completion-600.json").write_text(json.dumps(semi))
    guide600 = w / "s6" / "guide-600.json"
    pc6 = r.run("complete_guide.py", str(draft), str(w / "s6" / "completion-600.json"), "-o", str(guide600))
    p3 = r.run("fonts.py", "report", "--guide", str(guide600), "-o", str(w / "s6" / "semibold-missing.json"), fonts=folder)
    f3 = face(load(w / "s6" / "semibold-missing.json"), "Evalprobe Semibold")
    shutil.copy(fix / "fontsrc" / "EvalprobeSemibold-Regular.ttf", folder / "EvalprobeSemibold-Regular.ttf")
    p4 = r.run("fonts.py", "report", "--guide", str(guide600), "-o", str(w / "s6" / "semibold.json"), fonts=folder)
    j4 = load(w / "s6" / "semibold.json")
    out["S6 no reference, a face the recipient may lack"] += [
        ("the guide with a weight-600 title completes", pc6.returncode == 0, pc6.stderr.strip()[-300:]),
        ("without the face weight_faces names for 600, the report exits 3 and reads that face missing",
         p3.returncode == 3 and f3.get("status") == "missing", f"exit {p3.returncode}, {f3}"),
        ("with its file, the report exits 0 and tells the recipient they need it too",
         p4.returncode == 0 and any("Evalprobe Semibold" in line for line in j4.get("recipient", [])), f"exit {p4.returncode}, {j4.get('recipient')}"),
    ]

    # S8: an embedded collection: face 0 allows embedding, face 1 is restricted
    folder = w / "s8" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    ref = fix / "deck-embedded-mixed.pptx"
    p1 = r.run("fonts.py", "report", str(ref), "-o", str(w / "s8" / "fonts.json"), fonts=folder)
    f1 = face(load(w / "s8" / "fonts.json"), "Evalprobe Serif")
    p2 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    out["S8 an embedded collection that holds a restricted face"] = [
        ("the report reads the face missing, because one face of the collection is restricted",
         p1.returncode == 3 and f1.get("status") == "missing" and f1.get("permission") == "restricted", str(f1)),
        ("extract, even with the confirmation, writes nothing and names the restricted face",
         p2.returncode != 0 and not font_files(folder) and "Evalprobe Locked" in (p2.stdout + p2.stderr), f"exit {p2.returncode}, {font_files(folder)}: {(p2.stdout + p2.stderr).strip()[-300:]}"),
    ]

    # S9: an embedded font, not wrapped, that maps only the characters the deck sets
    folder = w / "s9" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    ref = fix / "deck-embedded-raw-subset.pptx"
    p1 = r.run("fonts.py", "report", str(ref), "-o", str(w / "s9" / "fonts.json"), fonts=folder)
    f1 = face(load(w / "s9" / "fonts.json"), "Evalprobe Serif")
    p2 = r.run("fonts.py", "extract", str(ref), "--licence-confirmed", "eval: the user said they hold a licence", fonts=folder)
    out["S9 an embedded font that holds only the deck's characters"] = [
        ("the report reads the face missing, as a subset", p1.returncode == 3 and f1.get("status") == "missing"
         and any("subset" in e.get("unusable", "") for e in f1.get("embedded", [])), str(f1.get("embedded"))),
        ("extract, even with the confirmation, writes nothing", p2.returncode != 0 and not font_files(folder), f"exit {p2.returncode}, {font_files(folder)}"),
    ]

    # S10: a restricted face installed on the machine: the report, the ruler and the renderer agree
    sysfonts = w / "s10" / "installed"
    sysfonts.mkdir(parents=True, exist_ok=True)
    shutil.copy(fix / "fontsrc" / "EvalprobeLocked-Regular.ttf", sysfonts / "EvalprobeLocked-Regular.ttf")
    conf = w / "s10" / "fonts.conf"
    # the cache folder first: fontconfig writes to the first writable one
    conf.write_text(f'<?xml version="1.0"?><fontconfig><cachedir>{w / "s10" / "cache"}</cachedir>'
                    f'<include ignore_missing="no">/etc/fonts/fonts.conf</include><dir>{sysfonts}</dir></fontconfig>')
    installed = {"FONTCONFIG_FILE": str(conf), "LAYOUT_FONT_ROOTS": os.pathsep.join(("/usr/share/fonts", "/usr/local/share/fonts", str(sysfonts)))}
    folder = w / "s10" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    p1 = r.run("fonts.py", "report", str(fix / "deck-locked-named.pptx"), "-o", str(w / "s10" / "fonts.json"), fonts=folder, env=installed)
    j1 = load(w / "s10" / "fonts.json")
    f1 = face(j1, "Evalprobe Locked")
    p2 = r.run("render.py", str(fix / "deck-locked-named.pptx"), "--out", str(w / "s10" / "renders"), fonts=folder, env=installed)
    drawn = (load(w / "s10" / "renders" / "fonts.json").get("Evalprobe Locked") or {})
    out["S10 a restricted face installed on this machine"] = [
        ("the report resolves the installed face and exits 0", p1.returncode == 0 and f1.get("status") == "installed", f"exit {p1.returncode}, {f1}"),
        ("the report names no fonts-folder copy to make", "fonts folder" not in json.dumps(f1.get("note", "")) and not f1.get("warning"), str(f1.get("note") or f1.get("warning"))),
        ("the renderer draws the face from the same file the ruler measures", p2.returncode == 0 and drawn.get("fidelity") == "exact"
         and drawn.get("file") == f1.get("file"), f"{drawn} / {f1.get('file')}"),
    ]

    # S11: the skill the model loads holds no downloader, and states the rule
    shipped = [f for f in SKILL.rglob("*") if f.is_file() and not f.relative_to(SKILL).as_posix().startswith(("refs/files", "refs/library"))
               and "__pycache__" not in f.parts]
    code_hits, text_hits = [], []
    for f in shipped:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_code = f.suffix in (".py", ".sh") or text.startswith("#!")
        for n, line in enumerate(text.splitlines(), 1):
            where = f"{f.relative_to(SKILL)}:{n}: {line.strip()[:160]}"
            if is_code and DOWNLOADER.search(line) and not line.lstrip().startswith("#"):
                code_hits.append(where)
            if FETCH_SCRIPT.search(line) or FONT_PACKAGE.search(line):
                text_hits.append(where)
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    out["S11 the skill holds no downloader"] = [
        ("no script of the skill names a download command or a network module", not code_hits, "\n".join(code_hits[:10])),
        ("no file of the skill names a download script or a font package", not text_hits, "\n".join(text_hits[:10])),
        ("SKILL.md states the rule: never download a font, even when asked", bool(re.search(r"Never download[^.]*font[^.]*even when asked", skill_md)), ""),
    ]

    # S7: no command made a network call, and nothing outside the work folder changed
    attempts = r.network_attempts()
    caches_after = cache_listing()
    out["S7 no network use; nothing changed outside the work folder"] = [
        ("every command ran in a network namespace with no network", r.unshare, "unshare -rn available" if r.unshare else "unshare -rn is not available here: only the logs below apply"),
        ("every process was traced for every socket call", r.strace, "strace available" if r.strace else "strace is not installed"),
        ("no Python network event, no AF_INET or AF_INET6 call, no connect() to a local socket outside nscd and LibreOffice's pipes",
         not attempts, "\n".join(attempts[:20])),
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
