"""Title block: an optional kicker, one dominant claim, and a hairline closing the band.

Two arrangements:
`with_kicker` stacks the kicker over the title in a flex column and closes it with a
hairline; `no_kicker` is the same column without the kicker.

WHICH RULE PICKS THE VARIANT: the data, never the box. A kicker in the data gives
`with_kicker`, none gives `no_kicker`. Dropping a kicker the writer gave to make a
shallow band fit would be silent content loss, and a component has no channel to tell
the writer it did that; if the band is too shallow the solver descends the scale or
refuses, which the build reports. An explicit `data["variant"]` wins, and asking for
`with_kicker` with no kicker is refused rather than swapped.

The roles, the gap and the hairline are open through `data["roles"]` and `data["rule"]`
(false leaves the hairline out); each default left in place is in the component's
report, with the variant and why.

Kicker over title, not beside it: setting one text beside another needs a flex weight
for kicker against title.

The column gap is space.xs, not space.sm: on keybank (title 24pt, two lines in
the 8,229,600 x 1,143,000 band) the two space.sm gaps left the block 102,473 EMU over
the band, and the kicker reads as the title's label only when it sits tight to it.
"""

from __future__ import annotations

VARIANTS = ("with_kicker", "no_kicker")
#: today's constants, each open through data["roles"]
ROLES = {"kicker": "type.kicker", "kicker_ink": "color.ink_muted", "title": "type.title", "rule": "color.rule", "gap": "space.xs"}


def select_variant(data: dict) -> tuple[str, str]:
    kicker = str(data.get("kicker") or "")
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown title_block variant {requested!r}; it draws {list(VARIANTS)}")
        if requested == "with_kicker" and not kicker:
            raise ValueError("variant 'with_kicker' needs a kicker, and this data carries none")
        if requested == "no_kicker" and kicker:
            # content is never dropped in silence: the writer gave a kicker
            raise ValueError("variant 'no_kicker' would drop the kicker this data carries; leave the kicker out of the data instead")
        return str(requested), "asked for by the data"
    return ("with_kicker", "the data carries a kicker") if kicker else ("no_kicker", "the data carries no kicker")


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "tb")
    roles, report = guide["_api"]["choices"](data, "roles", ROLES, "title_block")
    variant, why = select_variant(data)
    report.insert(0, f"variant {variant}: {why}")
    rule = data.get("rule", True)
    if not isinstance(rule, bool):
        raise ValueError(f"rule is true (the closing hairline) or false, got {rule!r}")
    if "rule" not in data:
        report.append("rule: true (the default: a hairline closes the band)")
    children = []
    if variant == "with_kicker":
        children.append({"type": "element", "id": f"{pid}-kicker", "kind": "text",
                         "paragraphs": [{"role": roles["kicker"], "text": str(data["kicker"]), "ink_role": roles["kicker_ink"]}]})
    children.append({"type": "element", "id": f"{pid}-title", "kind": "text",
                     "paragraphs": [{"role": roles["title"], "text": str(data["title"])}]})
    if rule:
        # the hairline is a measured extent of one EMU in the column: a rule has a width,
        # never a share of the band
        children.append({"type": "element", "id": f"{pid}-rule", "kind": "rule", "line_role": roles["rule"],
                         "size": {"width_emu": None, "height_emu": 1}})
    return {"type": "region", "id": pid, "report": report,
            "layout": {"kind": "flex", "direction": "column", "gap_role": roles["gap"], "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
