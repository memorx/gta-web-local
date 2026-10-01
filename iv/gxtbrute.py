#!/usr/bin/env python3
"""Recover GXT key names by brute force (Jenkins hash of the lower-case key).

    python iv/gxtbrute.py <american.gxt> TABLE [TABLE...] [+EXTRAPREFIX ...]

For each table, tries PREFIX + FIELD + INDEX combinations and prints the keys it
found next to each row, in text order. This is how the key schemes used by
build_fill.py (LM_F_QUOTE_0, E_NAME_3, LCPDSNAME_12...) were found. The printed
rows are game text: keep the output local.
"""
import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gxtdump  # noqa: E402
from gxt2txt import jenkins  # noqa: E402

FIELDS = """HEAD HEADLINE HL H SUB SUBHEAD SUBHEADLINE SEC SECHEAD SEC_HEAD SECHEADLINE SEC_HEADLINE SUMMARY SUM
REP REPORTER AUTH AUTHOR BY NAME STORY BODY TEXT TXT PARA PAR P STR MAIN INFO TITLE TIT T DATE TIME
PHOTO PIC CAP CAPTION DESC URL LINK ADD ADDR WEB SITE LBL LABEL QUOTE Q USER AGE LOC JOB SEX BUILD LIKE LIKES
DISLIKE DISLIKES ABOUT FROM TO SUBJ SUBJECT MSG MESSAGE CONTENT SENDER S B R A C D E F I L M N O U V W X Y Z
FORENAME SURNAME FIRST LAST STATUS BIRTH DOB AFF AFFIL AFFILIATIONS RAP RAPSHEET NOTES NOTE CRIME ALIAS
POST COMMENT COM ENTRY BLOG NAV PREV NEXT MORE""".split()


def prefixes_for(table):
    base = re.sub(r"\d+$", "", table)
    num = re.findall(r"\d+$", table)
    out = {table, base, table[:2], table[:3], table[:4], base[:2], base[:3], base[:4]}
    if num:
        n = num[0]
        out |= {base + "_" + n, base[:2] + n, base[:3] + n, base[:4] + n, base[:2] + "_" + n, base[:3] + "_" + n}
    return sorted(p for p in out if p)


def brute(table, hashes, extra_prefixes=()):
    found = {}
    prefixes = list(prefixes_for(table)) + list(extra_prefixes)
    idx = [""] + [str(i) for i in range(0, 60)] + [f"{i:02d}" for i in range(0, 60)]
    seps = ["_", ""]
    for p, s1, f, s2, i in itertools.product(prefixes, seps, FIELDS, seps, idx):
        for cand in (f"{p}{s1}{f}{s2}{i}", f"{p}{s1}{i}{s2}{f}" if i else None):
            if cand and len(cand) <= 23:
                h = jenkins(cand.lower().encode())
                if h in hashes and h not in found:
                    found[h] = cand
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        sys.exit(__doc__)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    tables = gxtdump.tables(argv[0])
    extra = [a[1:] for a in argv[1:] if a.startswith("+")]
    for name in [a for a in argv[1:] if not a.startswith("+")]:
        rows = tables[name]
        hashes = {h for h, _ in rows}
        found = brute(name, hashes, extra)
        print(f"===== {name}: {len(found)}/{len(rows)}")
        for i, (h, s) in enumerate(rows):
            print(f"{i:3d} {found.get(h, '?'):24s} {s[:90]}")


if __name__ == "__main__":
    main()
