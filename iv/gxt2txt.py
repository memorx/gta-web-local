#!/usr/bin/env python3
"""Write american.txt ("KEY = text" lines) from GTA IV's american.gxt.

whm2html replaces text keys found in the pages (EYE_HOME_11, CAR_NAV_HOME...) with
the localized strings listed in this file. GXT keys are stored hashed (Jenkins
one-at-a-time over the lower-case key), so the key names are taken from the
KEY-like strings that appear inside the .whm pages and looked up by hash.
The game files are only read.

    python iv/gxt2txt.py <american.gxt>[,<fallback.gxt>...] <html dir with .whm> <out.txt>

The episodes do not carry the web texts of the base game; like the game, pass the
base american.gxt as a fallback after the episode's own file.
"""
import re
import struct
import sys
import zlib
from pathlib import Path


def jenkins(s: bytes) -> int:
    """Jenkins one-at-a-time hash, as used by GTA IV for GXT keys (lower-case key)."""
    h = 0
    for c in s:
        h = (h + c) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h


def read_gxt(path: Path) -> dict:
    """hash -> string for every table of a GTA IV .gxt (first occurrence wins)."""
    b = path.read_bytes()
    if b[4:8] != b"TABL":
        raise ValueError(f"{path} is not a GTA IV GXT file")
    n = struct.unpack_from("<I", b, 8)[0] // 12
    tables = [struct.unpack_from("<8sI", b, 12 + i * 12) for i in range(n)]
    out = {}
    for name, off in tables:
        name = name.rstrip(b"\0").decode()
        pos = off + (0 if name == "MAIN" else 8)
        if b[pos:pos + 4] != b"TKEY":
            raise ValueError(f"{path}: table {name} has no TKEY block")
        tkey = struct.unpack_from("<I", b, pos + 4)[0]
        pos += 8
        keys = [struct.unpack_from("<II", b, pos + i * 8) for i in range(tkey // 8)]
        pos += tkey
        if b[pos:pos + 4] != b"TDAT":
            raise ValueError(f"{path}: table {name} has no TDAT block")
        tdat = b[pos + 8: pos + 8 + struct.unpack_from("<I", b, pos + 4)[0]]
        for o, h in keys:
            e = o
            while e + 1 < len(tdat) and not (tdat[e] == 0 and tdat[e + 1] == 0):
                e += 2
            out.setdefault(h, tdat[o:e].decode("utf-16le", errors="replace"))
    return out


KEY_RE = re.compile(rb"(?<![A-Za-z0-9_])[A-Z][A-Z0-9_]{2,31}(?![A-Za-z0-9_])")


def whm_keys(html_dir: Path) -> set:
    """Candidate text keys: KEY-like ASCII strings inside the (zlib-packed) .whm pages."""
    keys = set()
    for whm in html_dir.rglob("*.whm"):
        raw = whm.read_bytes()
        if raw[:3] != b"RSC":
            continue
        try:
            d = zlib.decompressobj().decompress(raw[12:])
        except zlib.error:
            continue
        for m in KEY_RE.finditer(d):
            k = m.group(0)
            if b"_" in k:  # real keys contain an underscore
                keys.add(k.decode())
    return keys


def clean(v: str) -> str:
    # game formatting tokens: ~n~ line break, ~w~ colour, etc.
    v = v.replace("~n~", " ")
    v = re.sub(r"~[a-zA-Z0-9_]*~", "", v)
    return " ".join(v.split())


def write_txt(gxts: list, html_dir: Path, out: Path) -> tuple:
    table = {}
    for g in reversed(gxts):  # the first file wins
        table.update(read_gxt(g))
    keys = whm_keys(html_dir)
    lines = []
    for k in sorted(keys):
        h = jenkins(k.lower().encode())
        if h in table:
            lines.append(f"{k} = {clean(table[h])}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(table), len(keys), len(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        sys.exit(__doc__)
    gxts = [Path(x) for x in argv[0].split(",")]
    html_dir, out = Path(argv[1]), Path(argv[2])
    n_str, n_keys, hits = write_txt(gxts, html_dir, out)
    print(f"{gxts[0].name}: {n_str} strings, {n_keys} candidate keys in .whm, {hits} resolved -> {out}")


if __name__ == "__main__":
    main()
