#!/usr/bin/env python3
"""Contact sheets from the screenshots taken by tests/probe.mjs.

    python tests/sheets.py <probe report dir> <page regex> <out.png> [columns] [crop height]

Each tile shows the top of a page and its name; pages with problems are labelled in yellow
with F (failed requests), I (broken images), K (raw text keys), S (empty slots), C (console).
Needs Pillow (pip install -r requirements.txt).
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        sys.exit(__doc__)
    out_dir, rx, dest = Path(argv[0]), re.compile(argv[1]), Path(argv[2])
    cols = int(argv[3]) if len(argv) > 3 else 4
    crop_h = int(argv[4]) if len(argv) > 4 else 1400
    rep = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    items = [r for r in rep if rx.search(r["page"]) and r.get("shot")]
    cw, ch = 400, int(400 * crop_h / 1280) + 18
    rows = (len(items) + cols - 1) // cols
    im = Image.new("RGB", (cols * cw, max(1, rows) * ch), (30, 30, 30))
    d = ImageDraw.Draw(im)
    for i, r in enumerate(items):
        x, y = (i % cols) * cw, (i // cols) * ch
        try:
            s = Image.open(r["shot"]).convert("RGB")
            s = s.crop((0, 0, 1280, min(crop_h, s.height)))
            s.thumbnail((cw - 4, ch - 20))
            im.paste(s, (x + 2, y + 2))
        except Exception:
            pass
        flags = []
        for k, tag in (("failed", "F"), ("brokenImg", "I"), ("rawKeys", "K"), ("emptySlots", "S"), ("console", "C")):
            if r.get(k):
                flags.append(f"{tag}{len(r[k])}")
        d.text((x + 3, y + ch - 16), r["page"][-58:] + ("  [" + " ".join(flags) + "]" if flags else ""),
               fill=(255, 220, 0) if flags else (160, 255, 160))
    im.save(dest)
    print(dest, len(items))


if __name__ == "__main__":
    main()
