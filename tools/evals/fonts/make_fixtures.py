#!/usr/bin/env python3
"""Make the fixtures of the font evaluations. Downloads nothing and installs nothing.

    python3 -I tools/evals/fonts/make_fixtures.py OUT_DIR

The fixtures need fonts that this machine does not have. The script makes them from a
font that IS installed: it copies the file and gives the copy a new family name (name
table IDs 1, 2, 4, 6, 16 and 17) and, for some copies, a different OS/2 fsType. The copies
stay in OUT_DIR/fontsrc and are never installed. The base font is the first of BASE_FACES
that fontconfig has as a TrueType file. Liberation Serif and DejaVu Serif allow modified
copies under a new name (SIL OFL 1.1, Bitstream Vera licence).

OUT_DIR gets:
  fontsrc/EvalprobeSerif-Regular.ttf    fsType 0 (installable)
  fontsrc/EvalprobeSerif-Bold.ttf       fsType 0, the bold style (from the base font's bold)
  fontsrc/EvalprobeLocked-Regular.ttf   fsType 2 (restricted)
  deck-installed.pptx         text in two installed faces (Liberation Serif, Liberation Sans)
  deck-named.pptx             text in Evalprobe Serif; nothing embedded
  deck-embedded-ok.pptx       Evalprobe Serif embedded as EOT (installable)
  deck-embedded-restricted.pptx  Evalprobe Locked embedded as EOT (restricted)
  subset.pdf                  deck-named.pptx drawn by LibreOffice with Evalprobe Serif
                              visible to that one run only: the PDF holds a subset of it
The embedded-font decks follow ECMA-376 Part 1, 19.2.1.9 and 19.2.1.10 (p:embeddedFontLst)
and the W3C EOT submission (https://www.w3.org/submissions/EOT/), version 0x00020001, no
compression, no XOR. PowerPoint did not write them: no PowerPoint runs here.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

BASE_FACES = ("Liberation Serif", "DejaVu Serif")
PROBE = "Evalprobe Serif"
LOCKED = "Evalprobe Locked"
EOT_XOR_FLAG = 0x10000000  # W3C EOT, Flags: TTEMBED_XORENCRYPTDATA


def base_font(style: str = "") -> Path:
    for face in BASE_FACES:
        out = subprocess.run(["fc-match", "-f", "%{family}\t%{file}\t%{fontformat}", face + style], capture_output=True, text=True, timeout=30).stdout
        family, _, rest = out.partition("\t")
        path, _, fmt = rest.partition("\t")
        if family.split(",")[0] == face and fmt == "TrueType" and path.lower().endswith(".ttf"):
            return Path(path)
    sys.exit(f"none of {BASE_FACES} is installed as a TrueType file; the fixtures need one of them")


def checksum(b: bytes) -> int:
    b = b + b"\0" * (-len(b) % 4)
    return sum(struct.unpack(f">{len(b) // 4}I", b)) & 0xFFFFFFFF


def name_table(family: str, style: str) -> bytes:
    names = {1: family, 2: style, 4: f"{family} {style}", 6: f"{family}-{style}".replace(" ", ""), 16: family, 17: style}
    records, store = [], b""
    for nid, text in sorted(names.items()):
        for platform, encoding, language, raw in ((1, 0, 0, text.encode("mac_roman")), (3, 1, 0x409, text.encode("utf-16-be"))):
            records.append((platform, encoding, language, nid, len(raw), len(store)))
            store += raw
    records.sort()
    return struct.pack(">HHH", 0, len(records), 6 + 12 * len(records)) + b"".join(struct.pack(">6H", *r) for r in records) + store


def renamed(src: Path, family: str, fs_type: int, style: str = "Regular") -> bytes:
    """The sfnt with a new name table and fsType; checksums per the OpenType spec."""
    data = src.read_bytes()
    tables = {}
    for i in range(struct.unpack_from(">H", data, 4)[0]):
        tag, _, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag] = bytearray(data[off:off + length])
    tables[b"name"] = bytearray(name_table(family, style))
    struct.pack_into(">H", tables[b"OS/2"], 8, fs_type)
    struct.pack_into(">I", tables[b"head"], 8, 0)
    tags = sorted(tables)
    power = max(i for i in range(16) if 2 ** i <= len(tags))
    header = data[:4] + struct.pack(">HHHH", len(tags), 16 * 2 ** power, power, 16 * len(tags) - 16 * 2 ** power)
    offset, directory, body = 12 + 16 * len(tags), b"", b""
    for tag in tags:
        b = bytes(tables[tag])
        directory += struct.pack(">4sIII", tag, checksum(b), offset + len(body), len(b))
        body += b + b"\0" * (-len(b) % 4)
    font = bytearray(header + directory + body)
    head_at = struct.unpack_from(">I", directory, 16 * tags.index(b"head") + 8)[0]
    struct.pack_into(">I", font, head_at + 8, (0xB1B0AFBA - checksum(bytes(font))) & 0xFFFFFFFF)
    return bytes(font)


def eot(font: bytes, family: str, xor: bool = False) -> bytes:
    """W3C EOT version 0x00020001 around the sfnt bytes: little-endian header, then the font."""
    tables = {struct.unpack_from(">4s", font, 12 + 16 * i)[0]: struct.unpack_from(">II", font, 12 + 16 * i + 8)
              for i in range(struct.unpack_from(">H", font, 4)[0])}
    os2 = font[tables[b"OS/2"][0]:][:96]
    weight, fs_type = struct.unpack_from(">H", os2, 4)[0], struct.unpack_from(">H", os2, 8)[0]
    checksum_adjustment = struct.unpack_from(">I", font, tables[b"head"][0] + 8)[0]
    data = bytes(b ^ 0x50 for b in font) if xor else font

    def name(text: str) -> bytes:
        raw = text.encode("utf-16-le")
        return struct.pack("<HH", 0, len(raw)) + raw

    head = struct.pack("<III", len(data), 0x00020001, EOT_XOR_FLAG if xor else 0) + os2[32:42] + struct.pack("<BB", 1, 0)
    head += struct.pack("<IHH", weight, fs_type, 0x504C) + os2[42:58] + struct.pack("<II", *struct.unpack_from(">II", os2, 78))
    head += struct.pack("<I", checksum_adjustment) + b"\0" * 16
    head += name(family) + name("Regular") + name("Version 1.0") + name(f"{family} Regular") + name("")
    return struct.pack("<I", 4 + len(head) + len(data)) + head + data


def deck(path: Path, faces: list[str]) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i, face in enumerate(faces):
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5 + 1.4 * i), Inches(9), Inches(1.2))
        run = box.text_frame.paragraphs[0].add_run()
        run.text = f"Quarterly revenue rose 12% on wider margins, set in {face}"
        run.font.name = face
        run.font.size = Pt(24)
    prs.save(str(path))


def embed(src: Path, dst: Path, family: str, blob: bytes) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename == "[Content_Types].xml":
                data = data.replace(b"<Default ", b'<Default Extension="fntdata" ContentType="application/x-fontdata"/><Default ', 1)
            elif info.filename == "ppt/_rels/presentation.xml.rels":
                data = data.replace(b"</Relationships>", b'<Relationship Id="rIdFont1" Type="http://schemas.openxmlformats.org/'
                                    b'officeDocument/2006/relationships/font" Target="fonts/font1.fntdata"/></Relationships>')
            elif info.filename == "ppt/presentation.xml":
                listing = (f'<p:embeddedFontLst><p:embeddedFont><p:font typeface="{escape(family)}" charset="0"/>'
                           '<p:regular r:id="rIdFont1"/></p:embeddedFont></p:embeddedFontLst>')
                text = re.sub(r"(<p:notesSz[^>]*/>)", lambda m: m.group(1) + listing, data.decode(), count=1)
                data = text.replace("<p:presentation ", '<p:presentation embedTrueTypeFonts="1" ', 1).encode()
            zout.writestr(info, data)
        zout.writestr("ppt/fonts/font1.fntdata", blob)


def subset_pdf(deck_path: Path, font: Path, out: Path) -> None:
    """LibreOffice draws the deck with the probe font visible to this one run only."""
    with tempfile.TemporaryDirectory(prefix="evalfix-") as tmp:
        t = Path(tmp)
        (t / "fonts").mkdir()
        shutil.copy(font, t / "fonts" / font.name)
        (t / "fonts.conf").write_text(f'<?xml version="1.0"?><fontconfig><cachedir>{escape(str(t / "cache"))}</cachedir>'
                                      f'<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                                      f'<dir>{escape(str(t / "fonts"))}</dir></fontconfig>')
        env = {**os.environ, "FONTCONFIG_FILE": str(t / "fonts.conf"), "HOME": str(t)}
        subprocess.run(["soffice", f"-env:UserInstallation=file://{t / 'profile'}", "--headless", "--norestore", "--nolockcheck",
                        "--convert-to", "pdf", "--outdir", str(t), str(deck_path)], env=env, capture_output=True, timeout=600, check=True)
        shutil.copy(t / (deck_path.stem + ".pdf"), out)


def main(out_dir: str) -> int:
    out = Path(out_dir).resolve()
    (out / "fontsrc").mkdir(parents=True, exist_ok=True)
    base = base_font()
    probe = renamed(base, PROBE, 0)
    locked = renamed(base, LOCKED, 2)
    (out / "fontsrc" / "EvalprobeSerif-Regular.ttf").write_bytes(probe)
    (out / "fontsrc" / "EvalprobeLocked-Regular.ttf").write_bytes(locked)
    (out / "fontsrc" / "EvalprobeSerif-Bold.ttf").write_bytes(renamed(base_font(":bold"), PROBE, 0, "Bold"))
    deck(out / "deck-installed.pptx", ["Liberation Serif", "Liberation Sans"])
    deck(out / "deck-named.pptx", [PROBE])
    deck(out / "deck-locked-named.pptx", [LOCKED])
    embed(out / "deck-named.pptx", out / "deck-embedded-ok.pptx", PROBE, eot(probe, PROBE))
    embed(out / "deck-locked-named.pptx", out / "deck-embedded-restricted.pptx", LOCKED, eot(locked, LOCKED))
    subset_pdf(out / "deck-named.pptx", out / "fontsrc" / "EvalprobeSerif-Regular.ttf", out / "subset.pdf")
    print(f"fixtures in {out}, made from {base}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
