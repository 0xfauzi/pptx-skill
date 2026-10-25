#!/usr/bin/env python3
"""The annotation layer (placeholder while the geometry is measured)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_pptx import MSO_SHAPE, Emu, _insert_fill_first, _set_line, _solid_fill, _without_theme_style, etree, qn  # noqa: E402


def write_filled_rect(slide, box: tuple[int, int, int, int], fill_hex: str, name: str):
    x, y, w, h = box
    shape = _without_theme_style(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(max(1, w)), Emu(max(1, h))))
    shape.name = name
    _solid_fill(shape._element.spPr, fill_hex)
    _set_line(shape._element.spPr, None, None)
    return shape
