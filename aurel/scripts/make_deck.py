"""Write deck.json and plan.json for the Aurel One launch keynote. Every product figure is a named placeholder."""
import json, os
D = "/home/user/pptx-skill/aurel"
IMG = f"{D}/img"

def lay(direction, gap, pad=None, align="stretch", justify="start"):
    return {"kind": "flex", "direction": direction, "gap_role": gap, "pad_role": pad, "align": align, "justify": justify}
def col(id, children, gap="space.md", pad=None, align="stretch", justify="start", weight=None, **kw):
    n = {"type": "region", "id": id, "layout": lay("column", gap, pad, align, justify), "children": children, **kw}
    if weight is not None: n["weight"] = weight
    return n
def row(id, children, gap="space.gutter", pad=None, align="stretch", justify="start", weight=None, **kw):
    n = {"type": "region", "id": id, "layout": lay("row", gap, pad, align, justify), "children": children, **kw}
    if weight is not None: n["weight"] = weight
    return n
def txt(id, paras, weight=None, anchor=None):
    n = {"type": "element", "id": id, "kind": "text", "paragraphs": paras}
    if weight is not None: n["weight"] = weight
    if anchor: n["anchor"] = anchor
    return n
def p(role, text, align=None, ink=None):
    d = {"role": role, "text": text}
    if align: d["align"] = align
    if ink: d["ink_role"] = ink
    return d
def img(id, weight=1.0):
    return {"type": "element", "id": id, "kind": "image", "weight": weight}
def spacer(id, weight=1.0):
    return {"type": "region", "id": id, "layout": lay("column", "space.xs"), "children": [], "weight": weight}
def hrule(id, role="color.accent1"):
    return {"type": "element", "id": id, "kind": "rule", "size": {"width_emu": None, "height_emu": 38100}, "line_role": role, "line_width_emu": 25400}
def disc(id):
    return {"type": "element", "id": id, "kind": "rect", "size": {"width_emu": 1828800, "height_emu": 1828800},
            "fill_role": "color.surface_alt", "line_role": "color.rule", "line_width_emu": 19050, "prst": "ellipse"}
def root(children, justify="start", gap="space.lg"):
    return {"root": col("root", children, gap=gap, pad="space.margin", justify=justify)}
def svg(name, align="center", valign="middle"):
    return {"svg": f"{IMG}/{name}.svg", "align": align, "valign": valign}

slides, pages = [], []
def page(id, spec, register, plan, images=None, title_el=None, notes=None):
    s = {"id": id, "layout": "Blank", "spec": spec, "title": {"register": register}}
    if title_el: s["title"]["element"] = title_el
    if images: s["images"] = images
    if notes: s["notes"] = notes
    slides.append(s)
    pages.append({"id": id, "title_register": register, **plan})

NOFIG = "Placeholder: figure to be supplied by Aurel."

# 1 cover
page("s01-cover", root([
        spacer("top", 1.0),
        txt("event", [p("type.kicker", "[Event name]  ·  [Date]")]),
        txt("name", [p("type.display", "Aurel")]),
        spacer("bottom", 0.35)], gap="space.sm"),
     "other: the company name as the page's only statement",
     {"intent": "open the keynote on the company, keeping the product name for the reveal", "message": "Aurel", "composition": "new:name-low-left",
      "deliberate_parallel": None, "exhibits": []}, title_el="name",
     notes="Hold on this page while the room settles.")

# 2 the problem
page("s02-loud", root([
        txt("title", [p("type.title", "The world is loud.")]),
        img("noise", 1.0)]),
     "claim",
     {"intent": "name the problem the product solves", "message": "The world is loud",
      "composition": "new:statement-over-wave", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "noise as a dense, uneven wall that fills the page",
        "comparison": "nothing yet: it sets up the next page, where the same bars fall silent",
        "data": "no data: an illustrative waveform of seventy two uneven bars",
        "forms_considered": [{"form": "full width waveform bars", "reason": "chosen: reads as sound at a glance and can be reused to show it stopping"},
                             {"form": "a photograph of a crowded street", "reason": "none supplied, and the user asked for type and shapes"},
                             {"form": "the statement alone on a black page", "reason": "the room hears the claim but sees nothing to set up the silence that follows"}],
        "chosen_form": "full width waveform bars", "why": "the waveform is the subject's own material and carries over to the next two pages",
        "marks": "no marks: grey bars only, so the gold on the next page is the first colour the room sees"}]},
     images={"noise": svg("noise")}, notes="Draft copy. Speak to the commute, the open office, the flight.")

# 3 the turn
page("s03-quiet", root([
        txt("title", [p("type.title", "Now, turn it down.")]),
        img("quiet", 1.0)]),
     "claim",
     {"intent": "turn from problem to promise", "message": "Aurel One turns the noise down",
      "composition": "new:statement-over-wave",
      "deliberate_parallel": "the same frame and the same bars as the page before, so the room sees the noise fall to a gold line rather than a new picture",
      "exhibits": [{"reader_must_see": "the same noise falling away to a single flat gold line",
        "comparison": "this page's waveform against the one on the page before",
        "data": "no data: the previous page's bars, decaying over the right half to a flat line",
        "forms_considered": [{"form": "decaying waveform ending in a gold line", "reason": "chosen: the change from noise to silence is drawn in one picture"},
                             {"form": "two waveforms side by side, before and after", "reason": "halves each wave and makes the room compare instead of watch it stop"}],
        "chosen_form": "decaying waveform ending in a gold line", "why": "it repeats page two's bars exactly, so the only change is the silence",
        "marks": "the flat line in gold, the first use of the product's colour"}]},
     images={"quiet": svg("quiet")})

# 4 reveal
page("s04-reveal", root([
        spacer("above", 1.0),
        txt("intro", [p("type.kicker", "Introducing")]),
        txt("name", [p("type.display", "Aurel One")]),
        hrule("line"),
        txt("line1", [p("type.body", "Noise-cancelling headphones from Aurel.")]),
        spacer("below", 0.6)], gap="space.sm"),
     "other: the product name revealed",
     {"intent": "reveal the product", "message": "Introducing Aurel One, noise-cancelling headphones",
      "composition": "new:name-on-gold-line", "deliberate_parallel": None,
      "exhibits": []}, title_el="name")

# 5 ANC figure
page("s05-silence", root([
        row("body", [
          col("figure", [
            txt("k", [p("type.kicker", "Active noise cancelling")]),
            txt("fig", [p("type.figure", "[XX] dB", ink="color.accent1")]),
            txt("line", [p("type.body", "less of the world around you.")])], gap="space.sm", justify="center", weight=1.1),
          col("compare", [
            txt("without", [p("type.caption", "Without")]),
            img("noise", 1.0),
            txt("with", [p("type.caption", "With Aurel One")]),
            img("quiet", 1.0)], gap="space.sm", weight=1.0)], weight=1.0),
        txt("note", [p("type.footnote", "[XX] dB: noise reduction and test conditions to be supplied by Aurel engineering. Waveforms are illustrations, not measurements.")])]),
     "other: one headline figure with its label",
     {"intent": "state the headline noise-cancelling figure", "message": "Aurel One removes [XX] dB of noise (placeholder)",
      "composition": "new:figure-beside-pair", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "the noise-reduction figure first, then what it means: the same noise without and with the headphones",
        "comparison": "the waveform without the headphones against the waveform with them",
        "data": "one figure in decibels, not yet supplied, and two illustrative waveforms",
        "forms_considered": [{"form": "big figure beside a stacked before and after pair", "reason": "chosen: the figure is the claim, the pair says what it feels like"},
                             {"form": "bar chart of decibel reduction against competitors", "reason": "no competitor figures exist, and a chart of placeholders would mean nothing"},
                             {"form": "big figure alone", "reason": "a decibel figure means little to a launch audience without a picture of it"}],
        "chosen_form": "big figure beside a stacked before and after pair", "why": "the room reads the figure in gold, then sees it as noise gone",
        "marks": "the figure in gold; the pair labelled Without and With Aurel One; the footnote says the waves are illustrations"}]},
     images={"noise": svg("noise"), "quiet": svg("quiet")}, title_el="fig")

# 6 sound
page("s06-sound", root([
        row("body", [
          img("rings", 1.0),
          col("words", [
            txt("k", [p("type.kicker", "Sound")]),
            txt("title", [p("type.title", "Hear only what you choose to.")]),
            txt("line", [p("type.body", "[XX] mm drivers, tuned by [team or partner].")])], gap="space.sm", justify="center", weight=1.2)], weight=1.0)]),
     "claim",
     {"intent": "turn from silence to sound quality", "message": "With the noise gone, the music is what is left",
      "composition": "new:shape-left-words-right", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "a driver: the source of the sound, with a gold centre",
        "comparison": "none: a single object that stands for the sound system",
        "data": "no data: driver size not yet supplied",
        "forms_considered": [{"form": "concentric driver rings with a gold core", "reason": "chosen: a driver's own shape, drawn plainly"},
                             {"form": "a frequency response curve", "reason": "no measurement supplied, and a curve asks the room to read axes"},
                             {"form": "an exploded drawing of the earcup", "reason": "no engineering drawings supplied; inventing one would misdescribe the product"}],
        "chosen_form": "concentric driver rings with a gold core", "why": "it carries the gold of the product to the sound, with no figure needed",
        "marks": "the core ring and dot in gold; the outer rings in the rule colour"}]},
     images={"rings": svg("rings")})

# 7 weight
page("s07-light", root([
        row("body", [
          spacer("gap", 1.0),
          col("figure", [
            txt("k", [p("type.kicker", "Comfort")]),
            txt("fig", [p("type.display", "[XXX] g")]),
            hrule("line", "color.rule"),
            txt("line1", [p("type.body", "Light enough to forget you are wearing them.")])], gap="space.sm", justify="center", weight=1.4)], weight=1.0),
        txt("note", [p("type.footnote", "[XXX] g: weight to be supplied by Aurel.")])]),
     "other: one headline figure with its label",
     {"intent": "comfort, in one figure", "message": "Aurel One weighs [XXX] g (placeholder)",
      "composition": "new:figure-right", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "the weight in grams, large, with nothing competing",
        "comparison": "none on the page; the presenter supplies any comparison aloud",
        "data": "one figure in grams, not yet supplied",
        "forms_considered": [{"form": "big figure set to the right of an empty field", "reason": "chosen: the empty field reads as lightness and varies the page from the figure page before"},
                             {"form": "figure beside a balance-scale icon", "reason": "a clip-art scale adds a mark with no job beyond the figure"}],
        "chosen_form": "big figure set to the right of an empty field", "why": "one number and space around it is the plainest way to say light",
        "marks": "no gold here: the gold is kept for noise cancelling and the product name; a grey rule under the figure"}]}, title_el="fig")

# 8 battery
def battery_block(id, fig, line):
    return col(id, [txt(f"{id}-fig", [p("type.figure", fig)]), txt(f"{id}-line", [p("type.body", line)])], gap="space.sm", weight=1.0)
page("s08-battery", root([
        col("head", [txt("k", [p("type.kicker", "Battery")]), txt("title", [p("type.title", "Power for the whole trip.")])], gap="space.xs"),
        row("body", [
          battery_block("play", "[XX] h", "on one charge, noise cancelling on."),
          {"type": "element", "id": "divider", "kind": "rule", "size": {"width_emu": 12700, "height_emu": None}, "line_role": "color.rule", "line_width_emu": 12700},
          battery_block("charge", "[X] min", "of charging gives [X] hours more.")], weight=1.0, align="center"),
        txt("note", [p("type.footnote", "Battery and charging figures and their test conditions to be supplied by Aurel.")])]),
     "claim",
     {"intent": "battery life and fast charge", "message": "[XX] hours on a charge, [X] hours from [X] minutes (placeholders)",
      "composition": "new:two-figures-divided", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "two figures side by side: how long a charge lasts and how fast it comes back",
        "comparison": "the full battery life beside the quick-charge figure, as two separate facts",
        "data": "two figures, hours and minutes, neither yet supplied",
        "forms_considered": [{"form": "two big figures split by a thin rule", "reason": "chosen: two co-equal facts, each read in one look"},
                             {"form": "a battery gauge filling up", "reason": "a gauge implies a proportion, and no figures exist to draw it from"},
                             {"form": "one figure with the second in the line under it", "reason": "fast charging is a selling point on its own and would be lost in a sentence"}],
        "chosen_form": "two big figures split by a thin rule", "why": "the two figures are co-equal, so they get one size and one baseline",
        "marks": "no colour: both figures in off-white, the rule in the rule colour"}]}, title_el="title")

# 9 features
def feature(i):
    return col(f"f{i}", [
        txt(f"f{i}-n", [p("type.kicker", f"0{i}")]),
        txt(f"f{i}-h", [p("type.h1", f"[Feature {i}]")]),
        txt(f"f{i}-b", [p("type.body", "[One line on what it does for the listener.]")])],
        gap="space.sm", pad="space.md", weight=1.0, fill_role="color.surface_alt")
page("s09-features", root([
        txt("title", [p("type.title", "Designed around the way you listen.")]),
        row("body", [feature(1), feature(2), feature(3)], gap="space.md", weight=1.0)]),
     "claim",
     {"intent": "the three features worth naming on stage", "message": "Three features, to be named by Aurel",
      "composition": "new:three-panels", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "three separate features, numbered, each with one line",
        "comparison": "three co-equal features, not ranked",
        "data": "three feature names and lines, none yet supplied",
        "forms_considered": [{"form": "three numbered panels in a row", "reason": "chosen: co-equal items read left to right at one size"},
                             {"form": "a bulleted list", "reason": "a list reads as small print from the back of a hall"},
                             {"form": "one page per feature", "reason": "the deck is capped at about twelve pages, and the figure pages need the room"}],
        "chosen_form": "three numbered panels in a row", "why": "three equal panels say the features are equal and keep each to one line",
        "marks": "numbers in gold as the only colour"}]})

# 10 finishes
def finish(i):
    return col(f"c{i}", [disc(f"c{i}-disc"), txt(f"c{i}-name", [p("type.caption", f"[Finish {i}]", align="center")])],
               gap="space.sm", align="center", weight=1.0)
page("s10-finishes", root([
        txt("title", [p("type.title", "Choose your finish.")]),
        row("body", [finish(1), finish(2), finish(3)], gap="space.md", align="center", weight=1.0),
        txt("note", [p("type.footnote", "Swatches are neutral placeholders: finish names, colours and count to be supplied by Aurel.")])]),
     "claim",
     {"intent": "the colourways", "message": "Aurel One comes in [N] finishes (placeholder)",
      "composition": "new:swatch-row", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "each finish as a large swatch with its name",
        "comparison": "the finishes against each other",
        "data": "finish names and colours, none yet supplied; three shown",
        "forms_considered": [{"form": "a row of large round swatches with names", "reason": "chosen: colour is the content, so the swatch is the exhibit"},
                             {"form": "product photographs in each finish", "reason": "Aurel has supplied no photography, and the user chose type and shapes"}],
        "chosen_form": "a row of large round swatches with names", "why": "round swatches echo the driver rings and each holds one colour",
        "marks": "none until colours are supplied: neutral fills with a rule outline, named placeholders under each"}]})

# 11 price
page("s11-price", root([
        spacer("above", 1.0),
        txt("k", [p("type.kicker", "Availability")]),
        txt("fig", [p("type.display", "[Price]", ink="color.accent1")]),
        txt("line", [p("type.body", "Pre-order [date] at [where]. In stores [date].")]),
        spacer("below", 1.0)], gap="space.sm"),
     "other: the price as the page's statement",
     {"intent": "price and availability", "message": "Aurel One costs [Price] and ships [date] (placeholders)",
      "composition": "new:figure-centre-left", "deliberate_parallel": None, "exhibits": []}, title_el="fig")

# 12 close
page("s12-close", root([
        txt("name", [p("type.display", "Aurel One")]),
        txt("url", [p("type.body", "[aurel web address]")]),
        img("quiet", 1.0)], gap="space.md"),
     "other: the product name as the closing statement",
     {"intent": "close on the name and the silence", "message": "Aurel One",
      "composition": "new:name-over-wave", "deliberate_parallel": None,
      "exhibits": [{"reader_must_see": "the product name over the noise falling to the gold line, as the keynote opened",
        "comparison": "the close against the opening pages, noise against silence",
        "data": "no data: the illustrative waveform of pages two and three",
        "forms_considered": [{"form": "name over the decaying waveform", "reason": "chosen: closes the loop the opening started"},
                             {"form": "the name alone, centred", "reason": "repeats the cover without the story told since"}],
        "chosen_form": "name over the decaying waveform", "why": "the last picture the room sees is the product's promise",
        "marks": "the flat line in gold"}]},
     images={"quiet": svg("quiet")}, title_el="name")

os.makedirs(f"{D}/deck", exist_ok=True)
json.dump({"slides": slides}, open(f"{D}/deck/deck.json", "w"), indent=1, ensure_ascii=False)
json.dump({"schema": "pptx-skill section plan v2", "reference_sha256": None, "pages": pages}, open(f"{D}/plan.json", "w"), indent=1, ensure_ascii=False)
print(len(slides), "slides")
