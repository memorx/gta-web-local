#!/usr/bin/env python3
"""Compare two probe reports (tests/probe.mjs) page by page.

    python tests/compare_probes.py <reference report.json> <new report.json> [--report out.json]

A page is "clean" when it has no failed requests, broken images, raw keys, empty slots
or console errors. Prints the totals of both runs and the pages whose problems differ.
Request URLs are compared without the server's address, so two servers on different
ports can be compared.
"""
import argparse
import json
import re
import sys
from pathlib import Path

KEYS = ("failed", "brokenImg", "rawKeys", "emptySlots", "console")


def load(p):
    rep = json.loads(Path(p).read_text(encoding="utf-8"))
    out = {}
    for r in rep:
        page = r["page"].lstrip("/")
        out[page] = {k: sorted(re.sub(r"https?://127\.0\.0\.1:\d+", "", x) for x in r.get(k, [])) for k in KEYS}
    return out


def clean(r):
    return not any(r[k] for k in KEYS)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare two probe reports page by page.")
    ap.add_argument("reference")
    ap.add_argument("new")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ref, new = load(a.reference), load(a.new)
    common = sorted(set(ref) & set(new))
    res = {
        "reference": {"pages": len(ref), "clean": sum(clean(r) for r in ref.values())},
        "new": {"pages": len(new), "clean": sum(clean(r) for r in new.values())},
        "only_in_reference": sorted(set(ref) - set(new)),
        "only_in_new": sorted(set(new) - set(ref)),
        "same_result": 0, "better": [], "worse": [], "different_problems": [],
    }
    for p in common:
        a_, b_ = ref[p], new[p]
        if a_ == b_:
            res["same_result"] += 1
        elif clean(b_) and not clean(a_):
            res["better"].append(p)
        elif clean(a_) and not clean(b_):
            res["worse"].append({"page": p, "new": b_})
        else:
            res["different_problems"].append({"page": p, "reference": a_, "new": b_})
    print(f"reference: {res['reference']['pages']} pages, {res['reference']['clean']} clean")
    print(f"new:       {res['new']['pages']} pages, {res['new']['clean']} clean")
    print(f"common pages: {len(common)} · same result: {res['same_result']} · better: {len(res['better'])} · "
          f"worse: {len(res['worse'])} · different problems: {len(res['different_problems'])}")
    print(f"only in reference: {len(res['only_in_reference'])} · only in new: {len(res['only_in_new'])}")
    for w in res["worse"][:20]:
        print("  worse:", w["page"], {k: v[:3] for k, v in w["new"].items() if v})
    for d in res["different_problems"][:20]:
        print("  different:", d["page"])
    if a.report:
        Path(a.report).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print("report:", a.report)


if __name__ == "__main__":
    main()
