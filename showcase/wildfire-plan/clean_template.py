"""Copy the template with the reference agency's document properties and layout prompt
texts replaced, so none of its names travel inside the new deck's package."""
import re
import sys
import zipfile
from xml.sax.saxutils import escape

src, dst = sys.argv[1], sys.argv[2]
CORE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>Wildfire-Risk Reduction Plan (illustrative)</dc:title>'
        '<dc:subject>Illustrative figures for a fictional program</dc:subject>'
        '<dc:creator>Ridgeline State Forestry Program (fictional)</dc:creator>'
        '<cp:lastModifiedBy></cp:lastModifiedBy><cp:revision>1</cp:revision>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-27T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-10-27T00:00:00Z</dcterms:modified>'
        '</cp:coreProperties>')
APP = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
       '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
       'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
       '<Application>Microsoft Office PowerPoint</Application><PresentationFormat>Widescreen</PresentationFormat>'
       '</Properties>')
PROMPTS = {"NNR.#": "RSFP.#"}
zin = zipfile.ZipFile(src)
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename == "docProps/core.xml":
            data = CORE.encode()
        elif info.filename == "docProps/app.xml":
            data = APP.encode()
        elif info.filename == "ppt/authors.xml":  # comment authors: names and account ids of the reference's staff
            data = re.sub(rb"<p188:author [^>]*/>", b"", data)
        elif info.filename.startswith("ppt/slideLayouts/slideLayout") and info.filename.endswith(".xml"):
            s = data.decode("utf-8")
            for a, b in PROMPTS.items():
                s = s.replace(f"<a:t>{a}</a:t>", f"<a:t>{escape(b)}</a:t>")
            s = re.sub(r"<a:t>Notes?: [^<]*</a:t>", "<a:t>Note:</a:t>", s)
            data = s.encode("utf-8")
        zout.writestr(info, data)
print(dst)
