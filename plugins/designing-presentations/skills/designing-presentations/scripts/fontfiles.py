"""Read a font file's names and embedding permission, and unwrap an embedded .pptx font.

    fontfiles.py FILE ...        print each face's names and fsType verdict as JSON

A font file from a reference or from the user is untrusted input. This module reads bytes
only: it never hands a file to a renderer, never runs anything, caps the file size, checks
every offset against the file length, and raises FontFileError with the reason. It reads
the sfnt or TTC header and table directory, `name` (family, style, full and PostScript
names), `OS/2` (version, weight, fsType, fsSelection), `head` (macStyle) and `cmap` (which
printable ASCII characters the face maps).

fsType (OpenType 1.9.1, OS/2 table: learn.microsoft.com/typography/opentype/spec/os2#fstype)
"indicates font embedding licensing rights": it decides whether a face may be embedded in
a document or taken out of one (EMBEDDABLE), not whether a face installed on this machine,
or supplied by the user, may be used on it. Every face is measured and rendered;
installable (0) and editable (8) may also be embedded and extracted; preview_print (4),
restricted (2), and a face with no OS/2 table (no permission stated) never.

A font embedded for one deck can hold only the characters that deck sets (a subset). The
EOT wrapper can say so (TTEMBED_SUBSET); the font itself cannot, so a face that does not
map every printable ASCII character (PRINTABLE_ASCII) is read as a subset: new text would
lack glyphs.

An embedded .pptx font part (ECMA-376 Part 1, 19.2.1.9 embeddedFont, 19.2.1.29 regular: a
relationship id and nothing else, so no key and no obfuscation) holds either the sfnt bytes
or an Embedded OpenType wrapper (W3C EOT submission, www.w3.org/submissions/EOT/): a
little-endian EMBEDDEDFONT header, then the font data, XORed with 0x50 when
TTEMBED_XORENCRYPTDATA is set, compressed with MicroType Express when TTEMBED_TTCOMPRESSED
is set (not decoded here: refused by name), a subset when TTEMBED_SUBSET is set.
"""

from __future__ import annotations

import io
import json
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

#: The largest font file installed on the measuring machine is 16,791,251 bytes
#: (wqy-zenhei.ttc, a CJK collection, the largest of 117 files). Four times that leaves room
#: for a larger CJK family and refuses a file no deck face needs.
MAX_FONT_BYTES = 64 * 1024 * 1024
#: TTC numFonts is a uint32, so a 12-byte header can claim four billion faces. The most
#: measured on the 117 installed files is 3 (wqy-zenhei.ttc); 64 is twenty times that.
MAX_FACES = 64

FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc"})
SFNT_TAGS = frozenset({b"\x00\x01\x00\x00", b"OTTO", b"true"})

# W3C EOT: Flags bits, the magic number, and the versions the submission defines
EOT_SUBSET = 0x00000001
EOT_MTX = 0x00000004
EOT_XOR = 0x10000000
EOT_XOR_KEY = 0x50
EOT_MAGIC = 0x504C
EOT_VERSIONS = frozenset({0x00010000, 0x00020001, 0x00020002})
EOT_FIXED_HEADER = 82  # the fixed fields end at byte 80 and a 2-byte name size follows: no header is shorter

#: the fsType verdicts that allow embedding a face, and so extracting it from a deck;
#: fsType never limits use on the machine that has the face
EMBEDDABLE = frozenset({"installable", "editable"})
#: U+0020 to U+007E, the 95 printable ASCII characters. Of the 118 faces installed on the
#: measuring machine, 113 map all 95; the 5 that do not set no Latin text (OpenSymbol, Noto
#: Color Emoji, three Unifont supplementary-plane faces). A face embedded for one deck's text
#: maps only the characters that text sets. Measured by tools/measure/font_probe.py, item 6.
PRINTABLE_ASCII = frozenset(range(0x20, 0x7F))


class FontFileError(ValueError):
    """The file is not a font this module can read safely; the message says why."""


@dataclass(frozen=True)
class FaceInfo:
    path: str
    index: int
    family: str            # name ID 16 when present, else name ID 1
    style: str             # name ID 17 when present, else name ID 2
    legacy_family: str     # name ID 1: the family name a .pptx names
    full_name: str
    postscript: str
    weight: int
    bold: bool
    italic: bool
    os2_version: int | None
    fs_type: int | None
    embedding: str         # installable | editable | preview_print | restricted
    bitmap_only: bool
    no_subsetting: bool
    ascii_unmapped: int    # printable ASCII characters the cmap does not map; 95 with no readable cmap

    def embeddable(self) -> bool:
        """Whether fsType allows embedding the face, or extracting it from a deck;
        bitmap-only embedding embeds no outline, so no."""
        return self.embedding in EMBEDDABLE and not self.bitmap_only


def embedding_of(fs_type: int | None, os2_version: int | None) -> tuple[str, bool, bool]:
    """(permission, bitmap_only, no_subsetting) from fsType. No OS/2 table states no
    permission: restricted. Bits 0 to 3 hold one of 0, 2, 4 or 8. A version 0 to 2 table
    may set several, and then the least restrictive takes precedence (the spec's Version
    differences); a version 3 or later table that sets several, or the reserved bit 0, is
    invalid and read as restricted."""
    if fs_type is None:
        return "restricted", False, False
    usage, bitmap_only, no_subsetting = fs_type & 0x000F, bool(fs_type & 0x0200), bool(fs_type & 0x0100)
    single = {0: "installable", 2: "restricted", 4: "preview_print", 8: "editable"}
    if usage in single:
        return single[usage], bitmap_only, no_subsetting
    if (os2_version or 0) <= 2 and not usage & 0x1:
        for bit, name in ((0x8, "editable"), (0x4, "preview_print"), (0x2, "restricted")):
            if usage & bit:
                return name, bitmap_only, no_subsetting
    return "restricted", bitmap_only, no_subsetting


class _Reader:
    """Bounds-checked big-endian reads from a seekable file of known length."""

    def __init__(self, handle: BinaryIO, size: int, label: str) -> None:
        self.handle, self.size, self.label = handle, size, label

    def read(self, at: int, n: int) -> bytes:
        if at < 0 or n < 0 or at + n > self.size:
            raise FontFileError(f"{self.label}: {n} bytes at offset {at} lie past the end of the file ({self.size} bytes)")
        self.handle.seek(at)
        data = self.handle.read(n)
        if len(data) != n:
            raise FontFileError(f"{self.label}: short read at offset {at}")
        return data

    def u16(self, at: int) -> int:
        return struct.unpack(">H", self.read(at, 2))[0]

    def u32(self, at: int) -> int:
        return struct.unpack(">I", self.read(at, 4))[0]


def _tables(r: _Reader, offset: int) -> dict[bytes, tuple[int, int]]:
    if r.read(offset, 4) not in SFNT_TAGS:
        raise FontFileError(f"{r.label}: no TrueType or OpenType header at offset {offset}")
    count = r.u16(offset + 4)
    if count == 0:
        raise FontFileError(f"{r.label}: the font lists no tables")
    directory = r.read(offset + 12, 16 * count)  # a count the file cannot hold is refused here
    out: dict[bytes, tuple[int, int]] = {}
    for i in range(count):
        tag, _, start, length = struct.unpack_from(">4sIII", directory, 16 * i)
        if start + length > r.size:
            raise FontFileError(f"{r.label}: table {tag!r} runs past the end of the file")
        if tag in out:
            raise FontFileError(f"{r.label}: table {tag!r} is listed twice")
        out[tag] = (start, length)
    return out


def _decode(platform: int, encoding: int, raw: bytes) -> str | None:
    if platform in (0, 3):
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return None
    if platform == 1 and encoding == 0:
        return raw.decode("mac_roman")
    return None


def _names(r: _Reader, table: tuple[int, int]) -> dict[int, str]:
    start, length = table
    data = r.read(start, length)
    if length < 6:
        raise FontFileError(f"{r.label}: the name table is {length} bytes")
    _, count, storage = struct.unpack_from(">HHH", data, 0)
    if 6 + 12 * count > length:
        raise FontFileError(f"{r.label}: the name table's {count} records run past the table")
    best: dict[int, tuple[int, str]] = {}
    for i in range(count):
        platform, encoding, language, name_id, n, off = struct.unpack_from(">6H", data, 6 + 12 * i)
        a = storage + off
        if a + n > length:
            raise FontFileError(f"{r.label}: name record {name_id} runs past the name table")
        text = _decode(platform, encoding, data[a:a + n])
        if text is None:
            continue
        # Windows English first, then any Windows record, then Unicode, then Mac Roman English
        rank = 0 if (platform == 3 and language == 0x409) else 1 if platform == 3 else 2 if platform == 0 else 3 if language == 0 else 4
        if name_id not in best or rank < best[name_id][0]:
            best[name_id] = (rank, text.strip("\x00 "))
    return {k: v for k, (_, v) in best.items()}


def _cmap_ascii(r: _Reader, table: tuple[int, int] | None) -> frozenset[int]:
    """The printable ASCII characters a Unicode subtable of the cmap maps to a glyph other
    than 0 (formats 4 and 12, the two the OpenType spec names for Unicode text). A table
    that cannot be read maps nothing."""
    if table is None:
        return frozenset()
    start, length = table
    data = r.read(start, length)
    if length < 4:
        return frozenset()
    count = struct.unpack_from(">H", data, 2)[0]
    if 4 + 8 * count > length:
        raise FontFileError(f"{r.label}: the cmap table's {count} subtables run past the table")
    found: set[int] = set()
    for i in range(count):
        platform, encoding, at = struct.unpack_from(">HHI", data, 4 + 8 * i)
        if not (platform == 0 or (platform == 3 and encoding in (1, 10))) or at + 4 > length:
            continue
        fmt = struct.unpack_from(">H", data, at)[0]
        if fmt == 4 and at + 14 <= length:
            sub_len, seg2 = struct.unpack_from(">H", data, at + 2)[0], struct.unpack_from(">H", data, at + 6)[0]
            n = seg2 // 2
            if at + sub_len > length or 16 + 8 * n > sub_len:
                continue
            ends, starts = at + 14, at + 16 + 2 * n
            deltas, ranges = starts + 2 * n, starts + 4 * n
            for k in range(n):
                end, first = struct.unpack_from(">H", data, ends + 2 * k)[0], struct.unpack_from(">H", data, starts + 2 * k)[0]
                delta, offset = struct.unpack_from(">h", data, deltas + 2 * k)[0], struct.unpack_from(">H", data, ranges + 2 * k)[0]
                for c in range(max(first, 0x20), min(end, 0x7E) + 1):
                    if offset == 0:
                        glyph = (c + delta) & 0xFFFF
                    else:
                        g_at = ranges + 2 * k + offset + 2 * (c - first)
                        if g_at + 2 > at + sub_len:
                            continue
                        glyph = struct.unpack_from(">H", data, g_at)[0]
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    if glyph:
                        found.add(c)
        elif fmt == 12 and at + 16 <= length:
            sub_len, groups = struct.unpack_from(">I", data, at + 4)[0], struct.unpack_from(">I", data, at + 12)[0]
            if at + sub_len > length or 16 + 12 * groups > sub_len:
                continue
            for k in range(groups):
                first, end, glyph = struct.unpack_from(">III", data, at + 16 + 12 * k)
                for c in range(max(first, 0x20), min(end, 0x7E) + 1):
                    if glyph + c - first:
                        found.add(c)
    return frozenset(found & PRINTABLE_ASCII)


def _face(r: _Reader, offset: int, index: int) -> FaceInfo:
    tables = _tables(r, offset)
    if b"name" not in tables:
        raise FontFileError(f"{r.label}: no name table, so no family name to match")
    names = _names(r, tables[b"name"])
    family = names.get(16) or names.get(1)
    if not family:
        raise FontFileError(f"{r.label}: the name table names no family (name IDs 1 and 16)")
    os2_version = fs_type = None
    weight, bold, italic = 400, False, False
    if b"OS/2" in tables:
        start, length = tables[b"OS/2"]
        if length < 64:
            raise FontFileError(f"{r.label}: the OS/2 table is {length} bytes; fsSelection alone ends at byte 64")
        os2_version, weight, fs_type, selection = r.u16(start), r.u16(start + 4), r.u16(start + 8), r.u16(start + 62)
        italic, bold = bool(selection & 0x01), bool(selection & 0x20)
    elif b"head" in tables:
        mac_style = r.u16(tables[b"head"][0] + 44)
        bold, italic = bool(mac_style & 0x01), bool(mac_style & 0x02)
    permission, bitmap_only, no_subsetting = embedding_of(fs_type, os2_version)
    ascii_unmapped = len(PRINTABLE_ASCII - _cmap_ascii(r, tables.get(b"cmap")))
    return FaceInfo(r.label, index, family, names.get(17) or names.get(2) or "Regular", names.get(1) or family,
                    names.get(4) or "", names.get(6) or "", weight, bold, italic, os2_version, fs_type, permission,
                    bitmap_only, no_subsetting, ascii_unmapped)


def _faces(handle: BinaryIO, size: int, label: str) -> list[FaceInfo]:
    if size > MAX_FONT_BYTES:
        raise FontFileError(f"{label} is {size:,} bytes; the cap is {MAX_FONT_BYTES:,}")
    r = _Reader(handle, size, label)
    tag = r.read(0, 4)
    if tag == b"ttcf":
        count = r.u32(8)
        if count == 0 or count > MAX_FACES:
            raise FontFileError(f"{label}: the collection claims {count} faces; the cap is {MAX_FACES}")
        return [_face(r, r.u32(12 + 4 * i), i) for i in range(count)]
    if tag in (b"wOFF", b"wOF2"):
        raise FontFileError(f"{label} is a WOFF web font; supply the .ttf or .otf file of the same face")
    return [_face(r, 0, 0)]


def read_faces(path: str | Path) -> list[FaceInfo]:
    """Every face in a .ttf, .otf or .ttc file, read without loading the file whole."""
    p = Path(path)
    if p.is_symlink():
        raise FontFileError(f"{p} is a symbolic link; put the font file itself in the folder")
    if not p.is_file():
        raise FontFileError(f"{p} is not a regular file")
    with p.open("rb") as handle:
        return _faces(handle, p.stat().st_size, str(p))


def faces_in_bytes(data: bytes, label: str) -> list[FaceInfo]:
    return _faces(io.BytesIO(data), len(data), label)


@dataclass(frozen=True)
class Unwrapped:
    data: bytes            # the sfnt bytes
    wrapper: str           # "sfnt" or "eot"
    subset: bool           # the EOT says the font holds only the characters the deck set
    eot_fs_type: int | None


def unwrap_embedded(blob: bytes, label: str) -> Unwrapped:
    """The sfnt inside an embedded .pptx font part, refused by name when it cannot be read
    (MicroType Express compression, an unknown wrapper, a header that disagrees with its
    length)."""
    if len(blob) > MAX_FONT_BYTES:
        raise FontFileError(f"{label} is {len(blob):,} bytes; the cap is {MAX_FONT_BYTES:,}")
    if blob[:4] in SFNT_TAGS or blob[:4] == b"ttcf":
        return Unwrapped(blob, "sfnt", False, None)
    if len(blob) < EOT_FIXED_HEADER or struct.unpack_from("<H", blob, 34)[0] != EOT_MAGIC:
        raise FontFileError(f"{label}: neither a TrueType or OpenType font nor an EOT wrapper (no magic number 0x504C)")
    eot_size, data_size, version, flags = struct.unpack_from("<IIII", blob, 0)
    eot_fs_type = struct.unpack_from("<H", blob, 32)[0]
    if version not in EOT_VERSIONS:
        raise FontFileError(f"{label}: EOT version 0x{version:08X} is not one the W3C submission defines")
    if eot_size != len(blob) or data_size > eot_size - EOT_FIXED_HEADER:
        raise FontFileError(f"{label}: the EOT header gives {eot_size} bytes and {data_size} of font data; the part holds {len(blob)}")
    if flags & EOT_MTX:
        raise FontFileError(f"{label}: the font data is compressed with MicroType Express, which this skill does not decode; "
                            "ask the user for the font file itself")
    data = blob[eot_size - data_size:eot_size]
    if flags & EOT_XOR:
        data = bytes(b ^ EOT_XOR_KEY for b in data)
    if data[:4] not in SFNT_TAGS:
        raise FontFileError(f"{label}: the EOT's font data is not a TrueType or OpenType font")
    return Unwrapped(data, "eot", bool(flags & EOT_SUBSET), eot_fs_type)


def main(argv: list[str]) -> int:
    out = []
    for arg in argv:
        try:
            out.extend(asdict(f) for f in read_faces(arg))
        except FontFileError as error:
            out.append({"path": arg, "error": str(error)})
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main(sys.argv[1:]))
