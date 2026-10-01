#!/usr/bin/env python3
"""Build the GTA III, Vice City and San Andreas sites from the Internet Archive.

    python classic/build_classic.py [--config config.toml] [--only ID[,ID]] [--delay 0.8] [--workers 1]
                                    [--refresh] [--keep] [--offline]

Those games have no in-game internet: their "websites" are the sites Rockstar published
at the time (in-universe sites and promotional ones). This downloads them from the
Wayback Machine, repairs what the Archive does not have (classic/raw_fixes.py), rewrites
the links for local browsing and sets up Ruffle for the Flash content:

    <work>/classic/<GAME>/_raw/...        original bytes as served by the Archive (cache)
    <work>/classic/<GAME>/_manifest/...   the files of each site and the capture used
    <out>/classic/<GAME>/<host>/<path>    what the server shows under /iii/ /vc/ /sa/
    <out>/classic/_sites.json             the list of sites for the hub
    <out>/_ruffle/                        Ruffle {RUFFLE_VERSION} + rewrite.js

The files and captures of every site are pinned in classic/lock/<id>.json, so every
build downloads the same bytes (the Archive is asked for about 4,000 files, one every
--delay seconds; the cache makes later builds offline). --refresh lists the sites from
the CDX API again instead (see wayback_mirror.py).
"""
import argparse
import base64
import hashlib
import io
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from common.config import load_config  # noqa: E402
import build_hub_data  # noqa: E402
import wayback_mirror  # noqa: E402

SITES = HERE / "classic_sites.json"
LOCK = HERE / "lock"

# Ruffle (https://ruffle.rs), the web build published by the Ruffle project on npm.
RUFFLE_VERSION = "0.2.0-nightly.2026.1.22"
RUFFLE_URL = f"https://registry.npmjs.org/@ruffle-rs/ruffle/-/ruffle-{RUFFLE_VERSION}.tgz"
RUFFLE_SHA512 = "6vZck0Q0LG3MZ8cd22UvdLZgUrViyzHE6juxEJRyt05OA2jCLKgkXh0NSeDCeKkpnDW+ZQqhhTnzrLyUuiRydQ=="  # npm "integrity"
__doc__ = __doc__.replace("{RUFFLE_VERSION}", RUFFLE_VERSION)


def log(msg=""):
    print(msg, flush=True)


def get_ruffle(tools: Path) -> Path:
    """Download and unpack the pinned Ruffle package into <work>/tools/ruffle-<version>/."""
    dest = tools / f"ruffle-{RUFFLE_VERSION}"
    if (dest / "ruffle.js").exists():
        return dest
    log(f"[classic] downloading Ruffle {RUFFLE_VERSION}")
    with urllib.request.urlopen(urllib.request.Request(RUFFLE_URL, headers={"User-Agent": "gta-web-local build"}), timeout=300) as r:
        data = r.read()
    got = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != RUFFLE_SHA512:
        sys.exit(f"[classic] checksum mismatch for {RUFFLE_URL}")
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t.getmembers():
            name = m.name.split("/", 1)[-1]  # npm packs everything under package/
            if not m.isfile() or "/" in name or name.startswith("."):
                continue
            (tmp / name).write_bytes(t.extractfile(m).read())
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the GTA III / Vice City / San Andreas sites from the Internet Archive.")
    ap.add_argument("--config", help="config file (default: config.toml at the repository root)")
    ap.add_argument("--only", default="", help="comma-separated site ids (see classic/classic_sites.json)")
    ap.add_argument("--delay", type=float, default=0.8, help="seconds between the requests of each download worker (default 0.8)")
    ap.add_argument("--workers", type=int, default=1, help="parallel downloads from the Archive (default 1: it refuses connections when asked too fast)")
    ap.add_argument("--refresh", action="store_true", help="list the sites from the CDX API instead of the lock files")
    ap.add_argument("--keep", action="store_true", help="do not delete <out>/classic before writing it")
    ap.add_argument("--offline", action="store_true", help="only rebuild from the download cache, no network")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    cfg = load_config(a.config)
    out = cfg.out
    classic = out / "classic"
    cache = cfg.work / "classic"
    t0 = time.time()
    log(f"[classic] out:   {classic}\n[classic] cache: {cache}")
    ruffle = get_ruffle(cfg.tools)
    if classic.exists() and not a.keep and not a.only:
        shutil.rmtree(classic)
    args = [str(SITES), str(classic), "--cache", str(cache), "--lock", str(LOCK), "--delay", str(a.delay), "--workers", str(a.workers)]
    if a.only:
        args += ["--only", a.only]
    if a.refresh:
        args += ["--refresh", "--assets-pass", "--externals"]
    if a.offline:
        args += ["--rewrite-only"]
    try:
        stats = wayback_mirror.main(args)
    except wayback_mirror.CDXError as e:
        sys.exit(f"[classic] {e}")
    build_hub_data.build(SITES, out, ruffle, cache, log=lambda m: log(f"[classic] {m}"))
    n = sum(1 for p in classic.rglob("*") if p.is_file())
    log(f"[classic] done in {time.time() - t0:.0f}s: {n} files in {classic}")
    if stats and stats.get("changed"):
        log(f"[classic] note: {len(stats['changed'])} files are not the bytes pinned in the lock (see above)")


if __name__ == "__main__":
    main()
