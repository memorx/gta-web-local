#!/usr/bin/env python3
"""Compare two build outputs file by file (SHA-1), for reproducibility checks.

    python tests/compare_trees.py <reference dir> <new dir> [--html-normalize] [--exclude GLOB ...]
                                  [--report report.json]

--html-normalize  when two .html files differ, compare them again as token streams with
                  the attributes of every tag, and the declarations of every style="",
                  in sorted order (the GTA IV converter used to write them in random order).

Prints a summary and writes the full list of differences to --report.
"""
import argparse
import fnmatch
import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files(root: Path, excludes):
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, e) for e in excludes):
                continue
            out[rel] = p
    return out


class Tokens(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.t = []

    @staticmethod
    def attrs(attrs):
        norm = []
        for k, v in attrs:
            if k == "style" and v:
                v = ";".join(sorted(x.strip() for x in v.split(";") if x.strip()))
            norm.append((k, v))
        return tuple(sorted(norm, key=lambda kv: (kv[0], kv[1] or "")))

    def handle_starttag(self, tag, attrs):
        self.t.append(("s", tag, self.attrs(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.t.append(("se", tag, self.attrs(attrs)))

    def handle_endtag(self, tag):
        self.t.append(("e", tag))

    def handle_data(self, data):
        self.t.append(("d", data))

    def handle_entityref(self, name):
        self.t.append(("d", f"&{name};"))

    def handle_charref(self, name):
        self.t.append(("d", f"&#{name};"))

    def handle_comment(self, data):
        self.t.append(("c", data))

    def handle_decl(self, decl):
        self.t.append(("decl", decl.lower()))


def html_tokens(p: Path):
    parser = Tokens()
    parser.feed(p.read_bytes().decode("utf-8", "replace"))
    parser.close()
    # merge adjacent text chunks (the parser may split them differently)
    merged = []
    for tok in parser.t:
        if tok[0] == "d" and merged and merged[-1][0] == "d":
            merged[-1] = ("d", merged[-1][1] + tok[1])
        else:
            merged.append(tok)
    return merged


def compare(ref: Path, new: Path, html_normalize=False, excludes=()):
    a, b = files(ref, excludes), files(new, excludes)
    only_ref = sorted(set(a) - set(b))
    only_new = sorted(set(b) - set(a))
    same, normalized, differ = [], [], []
    for rel in sorted(set(a) & set(b)):
        if a[rel].stat().st_size == b[rel].stat().st_size and sha1(a[rel]) == sha1(b[rel]):
            same.append(rel)
        elif html_normalize and rel.lower().endswith((".html", ".htm")) and html_tokens(a[rel]) == html_tokens(b[rel]):
            normalized.append(rel)
        else:
            differ.append(rel)
    return {"reference": str(ref), "new": str(new), "files_reference": len(a), "files_new": len(b),
            "identical": len(same), "equal_after_normalizing": normalized, "different": differ,
            "only_in_reference": only_ref, "only_in_new": only_new}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare two build outputs file by file.")
    ap.add_argument("reference")
    ap.add_argument("new")
    ap.add_argument("--html-normalize", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], help="glob of relative paths to skip (repeatable)")
    ap.add_argument("--report", help="write the full result as JSON")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    r = compare(Path(a.reference), Path(a.new), a.html_normalize, a.exclude)
    print(f"reference: {r['files_reference']} files · new: {r['files_new']} files")
    print(f"identical (SHA-1): {r['identical']}")
    if a.html_normalize:
        print(f"equal after normalizing attribute order: {len(r['equal_after_normalizing'])}")
    print(f"different: {len(r['different'])} · only in reference: {len(r['only_in_reference'])} · only in new: {len(r['only_in_new'])}")
    for k in ("different", "only_in_reference", "only_in_new"):
        for rel in r[k][:25]:
            print(f"  {k}: {rel}")
        if len(r[k]) > 25:
            print(f"  ... {len(r[k]) - 25} more")
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"report: {a.report}")
    return 0 if not (r["different"] or r["only_in_reference"] or r["only_in_new"]) else 1


if __name__ == "__main__":
    sys.exit(main())
