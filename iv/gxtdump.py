#!/usr/bin/env python3
"""Read the tables of a GTA IV .gxt in text order (debug aid and library for build_fill.py).

    python iv/gxtdump.py <american.gxt> TABLE [TABLE...]

Prints, for each table, the row number, the key hash and the text. The output is
game text: keep it local, do not publish it.
"""
import struct
import sys
from pathlib import Path


def tables(path):
    """{table name: [(key hash, text), ...]} with the rows in the order they appear in the text block."""
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 8)[0] // 12
    out = {}
    for name, off in [struct.unpack_from("<8sI", b, 12 + i * 12) for i in range(n)]:
        name = name.rstrip(b"\0").decode()
        pos = off + (0 if name == "MAIN" else 8)
        tkey = struct.unpack_from("<I", b, pos + 4)[0]
        pos += 8
        keys = [struct.unpack_from("<II", b, pos + i * 8) for i in range(tkey // 8)]
        pos += tkey
        tdat = b[pos + 8:pos + 8 + struct.unpack_from("<I", b, pos + 4)[0]]
        strs = []
        for o, h in keys:
            e = o
            while e + 1 < len(tdat) and not (tdat[e] == 0 and tdat[e + 1] == 0):
                e += 2
            strs.append((o, h, tdat[o:e].decode("utf-16le", "replace")))
        strs.sort()
        out[name] = [(h, s) for _, h, s in strs]
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        sys.exit(__doc__)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    t = tables(argv[0])
    for name in argv[1:]:
        if name not in t:
            print(f"===== {name}: not in this file")
            continue
        print("=====", name, len(t[name]))
        for i, (h, s) in enumerate(t[name]):
            print(f"{i:3d} {h:08x} {s}")


if __name__ == "__main__":
    main()
