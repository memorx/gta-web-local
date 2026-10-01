"""Game text (GXT2) for the GTA V sites: the tables the host and the converter read.

Outputs (all generated from your own game files, in <work>/v/text):

  strings_global.json   every text of global.gxt2 by JOAAT hash: base (update2.rpf), each DLC
                        pack, then the update.rpf patch (later files win, as in the game).
                        Published as /v/_lib/strings_all.json (host fallback table).
  strings_web.json      {"LABEL": "text"} for the labels the sites, the browser script and the
                        data providers use (published as /v/_lib/strings.json). Candidates:
                        literals of the sites' ActionScript (JPEXS export), strings of the
                        browser script appinternet.ysc, labels named in v/providers/*.js,
                        families built at run time (BLE_<n>, NWS_*_HL<k>, DESC_<site>...);
                        each is hashed and kept if it exists in the GXT2 files given.
  www.epsilonprogram.com.json
                        the EPSWAUD dialogue lines (EPSW_VOICE<n>_<k>) the Epsilon provider
                        shows as subtitles; the provider names the labels, the text comes
                        from epswaud.gxt2.

GXT2 format (little endian): '2TXG' | u32 n | n x (u32 hash, u32 offset) | ... NUL-terminated
UTF-8 strings at absolute offsets. JOAAT (the game's atStringHash) of the lower-cased label:
    h=0; for each byte c: h+=c; h+=h<<10; h^=h>>6   (mod 2^32);  h+=h<<3; h^=h>>11; h+=h<<15
joaat("adder") = 0xB779A091.

    python v/gxt2json.py global <out.json> <global.gxt2> [<dlc/global.gxt2> ...] <patch/global.gxt2>
    python v/gxt2json.py web <out.json> --as <dir> [--as <dir>] --ysc <appinternet.ysc>
                         --providers <dir> [--host-data host_data.json] <gxt2> [<gxt2> ...]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import struct
import sys
import zlib


# ---- GXT2 and JOAAT -------------------------------------------------------------------
def read_gxt2(path: str) -> dict:
    """{'hex8 hash': text} of a GXT2 file."""
    with open(path, "rb") as fh:
        b = fh.read()
    if b[:4] != b"2TXG":
        raise ValueError("%s is not a GXT2 file" % path)
    count, = struct.unpack_from("<I", b, 4)
    out = {}
    for i in range(count):
        h, off = struct.unpack_from("<II", b, 8 + i * 8)
        end = b.index(b"\0", off)
        out["%08x" % h] = b[off:end].decode("utf-8", errors="replace")
    return out


def joaat(s: str) -> int:
    h = 0
    for c in s.lower().encode("utf-8"):
        h = (h + c) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h


assert joaat("adder") == 0xB779A091


# ---- strings of a compiled script (.ysc: RSC7 header + raw deflate) --------------------
def ysc_strings(path: str) -> list:
    """The string table of a GTA V script (Legacy RSC7 v10 or Enhanced v12)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:4] != b"RSC7":
        raise ValueError("%s is not an RSC7 script" % path)
    d = zlib.decompressobj(-15).decompress(raw[16:])

    def ptr(off: int) -> int:
        v = struct.unpack_from("<Q", d, off)[0]
        if v >> 28 not in (5, 6):
            raise ValueError("bad pointer %x in %s" % (v, path))
        return v & 0x0FFFFFFF
    blocks, size = ptr(0x68), struct.unpack_from("<I", d, 0x70)[0]
    table = bytearray()
    n = (size + 0x3FFF) >> 14
    for i in range(n):
        p = ptr(blocks + 8 * i)
        table += d[p:p + (0x4000 if i < n - 1 else size - 0x4000 * (n - 1))]
    return [s.decode("latin-1") for s in bytes(table).split(b"\0") if s]


# ---- strings_global.json -----------------------------------------------------------------
def build_global(out_path: str, files: list) -> int:
    table: dict = {}
    for p in files:
        table.update(read_gxt2(p))
    _write(out_path, json.dumps(table, ensure_ascii=False, separators=(",", ":")))
    return len(table)


# ---- strings_web.json --------------------------------------------------------------------
TOKEN = re.compile(r'"([A-Z][A-Z0-9_]{2,40})"')
LABEL = re.compile(r"[A-Z][A-Z0-9_]{2,40}")
# a literal concatenated AFTER something else: prefix + "WAITING_TO_PURCHASE"
SUFFIX = re.compile(r'\+\s*"([A-Z0-9][A-Z0-9_]{0,40})"')


def prefixed(prefixes, suffixes, numbers: int = 100) -> set:
    """Labels built at run time: PREFIX_ + suffix and PREFIX_ + n (e.g. VehicleWebsite's
    DESCRIPTION_LABEL_PREFIX "LGM_" + "WAITING_TO_PURCHASE"). All combinations are tried;
    the ones missing from the GXT2 fall out by themselves."""
    tails = set(suffixes) | {str(n) for n in range(numbers)}
    return {p + s for p in prefixes for s in tails}


def candidates(as_dirs: list, scripts: list, provider_dirs: list, host_data: str | None) -> set:
    labels, tails = set(), set()
    for d in as_dirs:
        for p in glob.glob(os.path.join(d, "**", "*.as"), recursive=True):
            with open(p, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            labels.update(TOKEN.findall(src))
            tails.update(SUFFIX.findall(src))
    # every string literal of the browser script that looks like a label
    for s in scripts:
        labels.update(x for x in ysc_strings(s) if LABEL.fullmatch(x))
    # data providers: labels between single or double quotes, and numeric families
    for d in provider_dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.js"))):
            with open(p, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            labels.update(TOKEN.findall(src))
            labels.update(re.findall(r"'([A-Z][A-Z0-9_]{2,40})'", src))
            for pre in re.findall(r"'([A-Z][A-Z0-9_]{1,30}_)'\s*\+", src):     # 'BSS_BSTR_' + n
                labels.update("%s%d" % (pre, n) for n in range(200))
    labels |= prefixed({lab for lab in labels if lab.endswith("_")}, tails)
    # labels the sites build at run time
    for n in range(0, 80):
        labels.update({"LAR_SP_%d_DESC" % n, "PIM_MSG_STY_D_%d" % n, "DYN_INTERIOR_DESCRIPTION_%d" % n})
    # bleets ("BLE_" + n, n < 480) and eyefind news ("NWS_..._HL" + k)
    labels.update("BLE_%d" % n for n in range(480))
    labels.add("BLE_BLANK")
    for lab in list(labels):
        if lab.startswith("NWS_") and (lab.endswith("_HL") or lab.endswith("_S")):
            labels.update(lab + str(k) for k in range(1, 10))
    # news events ported from the script (host_data.json: {"hl", "s", "variants": [[k, paper]]})
    if host_data and os.path.exists(host_data):
        with open(host_data, encoding="utf-8") as fh:
            for ev in json.load(fh).get("news", []):
                for k, _paper in ev.get("variants", []):
                    labels.update({"%s%d" % (ev["hl"], k), "%s%d" % (ev["s"], k)})
    labels.update("LFI_STRAPLINE%d" % n for n in range(0, 20))
    # eyefind builds "DESC_" + site id (website of the minute, search results)
    for lab in list(labels):
        if re.search(r"_(COM|NET|ORG|INFO|BIZ|US|TV|XXX)$", lab):
            labels.add("DESC_" + lab)
            if lab.startswith("WWW_"):
                labels.add("DESC_" + lab[4:])
    # map zones (eyefind shows the player's zone)
    labels.update(["DOWNT", "ROCKF", "VINE", "DELPE", "SANDY", "PALETO", "MIRR", "DAVIS", "VESP"])
    return labels


def build_web(out_path: str, files: list, labels: set) -> int:
    table: dict = {}
    for p in files:
        table.update(read_gxt2(p))
    out = {}
    for lab in sorted(labels):
        v = table.get("%08x" % joaat(lab))
        if v is not None:
            out[lab] = v
    # CRLF line ends on every platform: the published table has always been written that way
    # (it keeps the ?v= stamp of the pages stable between Windows and Linux builds)
    _write(out_path, json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), newline=CRLF)
    return len(out)


# ---- dialogue lines for a provider ---------------------------------------------------------
def export_labels(out_path: str, files: list, labels: list) -> int:
    """{label: raw text} of the given labels (later GXT2 files win)."""
    table: dict = {}
    for p in files:
        table.update(read_gxt2(p))
    out = {lab: table["%08x" % joaat(lab)] for lab in labels if "%08x" % joaat(lab) in table}
    _write(out_path, json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return len(out)


def provider_labels(path: str, pattern: str) -> list:
    """Labels a provider names (e.g. EPSW_VOICE<n>_<k>), in order of appearance."""
    with open(path, encoding="utf-8") as fh:
        found = re.findall(r"'(%s)'" % pattern, fh.read())
    return list(dict.fromkeys(found))


CRLF = "\r\n"


def _write(path: str, text: str, newline: str = "\n") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GTA V GXT2 text -> JSON tables for the GTA V sites.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("global", help="every global.gxt2 text by hash")
    g.add_argument("out")
    g.add_argument("gxt2", nargs="+")
    w = sub.add_parser("web", help="the labels the sites, the script and the providers use")
    w.add_argument("out")
    w.add_argument("gxt2", nargs="+")
    w.add_argument("--as", dest="as_dirs", action="append", default=[], help="JPEXS ActionScript export folder")
    w.add_argument("--ysc", action="append", default=[], help="appinternet.ysc")
    w.add_argument("--providers", action="append", default=[], help="folder with provider .js files")
    w.add_argument("--host-data", help="host_data.json (news labels)")
    a = ap.parse_args(argv)
    if a.cmd == "global":
        print("%d texts -> %s" % (build_global(a.out, a.gxt2), a.out))
    else:
        labels = candidates(a.as_dirs, a.ysc, a.providers, a.host_data)
        print("%d texts -> %s" % (build_web(a.out, a.gxt2, labels), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
