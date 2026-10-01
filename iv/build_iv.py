#!/usr/bin/env python3
"""Build the GTA IV in-game internet from your own copy of the game.

    python iv/build_iv.py [--config config.toml] [--only GTAIV,TLAD,TBoGT] [--keep]

Reads (never writes) the `gta4` folder of config.toml, the one that contains GTAIV.exe:
    pc/html/**/*.whm                  pages of the base game (RSC5 + zlib)
    TLAD/pc/html, TBoGT/pc/html       pages of the episodes, when installed
    <episode>/common/text/american.gxt  texts
    <episode>/pc/textures/*.wtd       textures shared by the pages (ads, news photos...)

Writes <out>/iv/<GTAIV|TLAD|TBoGT>/pc/html, served by server/gta_web.py under /iv/:
    <site>/<page>.html + images     converted by whm2html (third_party/gtaweb)
    _tex/<dictionary>/<name>.png    shared textures
    _fill/data.js, fill.js, fill.css  the layer that fills the slots the game fills from scripts
    ttf/DIN-Medium.woff2            the font the converter's pages ask for
and <out>/iv/<episode>/american.txt (the page texts used by the converter).

whm2html is built from third_party/gtaweb with Go. If `go` is not on PATH (or with
--pinned-go) Go {GO_VERSION} is downloaded from go.dev into <work>/tools/go and its
SHA-256 is checked.
"""
import argparse
import fnmatch
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from common.config import load_config  # noqa: E402
import build_fill  # noqa: E402
import gxt2txt  # noqa: E402

GTAWEB = REPO / "third_party" / "gtaweb"
EPISODES = [("GTAIV", ""), ("TLAD", "TLAD"), ("TBoGT", "TBoGT")]
# Texture dictionaries the web pages use, in each <episode>/pc/textures.
TEXTURE_PATTERNS = ["web*.wtd", "eyeadvert_*.wtd", "browser.wtd", "computer.wtd", "policecomputer.wtd",
                    "policedb*.wtd", "pdb*.wtd", "proc_mail.wtd"]

# Go used when there is none on PATH: the release the reference build was made with.
GO_VERSION = "1.27.1"
GO_SHA256 = {
    "windows-amd64.zip": "a3911b5e0e1b1053f25ed0675f4c1c6aad1e2bfcf253df2b9be4caabd2edd95d",
    "windows-arm64.zip": "13b69b87bb0e83f96bc68560a8cace7f0343b1e03469f1110ea18d17e3234069",
    "linux-amd64.tar.gz": "63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445",
    "linux-arm64.tar.gz": "3450b45a3f9ee8568792736a5c5e70a1f2e9b36c35a8f74958c03e51d7d92bec",
    "darwin-amd64.tar.gz": "8f8f52c6649542cf027bbc9b9c68d1ec042f9f34808a40413f0b8b3f66f3caa4",
    "darwin-arm64.tar.gz": "ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12",
}
EXE = ".exe" if os.name == "nt" else ""
__doc__ = __doc__.replace("{GO_VERSION}", GO_VERSION)


def log(msg=""):
    print(msg, flush=True)


def download(url: str, sha256: str) -> bytes:
    log(f"  downloading {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gta-web-local build"}), timeout=300) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        sys.exit(f"[iv] checksum mismatch for {url}: expected {sha256}, got {got}")
    return data


# ------------------------------------------------------------------ Go and whm2html

def go_platform() -> str:
    osname = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(sys.platform)
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower())
    ext = "zip" if osname == "windows" else "tar.gz"
    key = f"{osname}-{arch}.{ext}"
    if key not in GO_SHA256:
        sys.exit(f"[iv] no pinned Go download for this platform ({sys.platform} {platform.machine()}). "
                 f"Install Go {GO_VERSION} or newer and put it on PATH.")
    return key


def pinned_go(tools: Path) -> Path:
    goroot = tools / "go"
    gobin = goroot / "bin" / f"go{EXE}"
    stamp = goroot / "VERSION"
    if gobin.exists() and stamp.exists() and stamp.read_text(encoding="utf-8", errors="replace").startswith(f"go{GO_VERSION}"):
        return gobin
    key = go_platform()
    data = download(f"https://go.dev/dl/go{GO_VERSION}.{key}", GO_SHA256[key])
    if goroot.exists():
        shutil.rmtree(goroot)
    tools.mkdir(parents=True, exist_ok=True)
    if key.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tools)  # the archive holds a single go/ folder
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            t.extractall(tools, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(tools)
    if not gobin.exists():
        sys.exit(f"[iv] Go archive did not contain {gobin}")
    return gobin


def find_go(tools: Path, force_pinned: bool):
    """(go executable, environment) for building whm2html."""
    env = dict(os.environ)
    system_go = None if force_pinned else shutil.which("go")
    if system_go:
        return Path(system_go), env
    gobin = pinned_go(tools)
    env.update(GOTOOLCHAIN="local", GOPATH=str(tools / "gopath"), GOCACHE=str(tools / "gocache"),
               GOROOT=str(gobin.parent.parent))
    return gobin, env


def build_converter(tools: Path, gtaweb: Path, force_pinned: bool, rebuild: bool) -> Path:
    if not (gtaweb / "go.mod").exists():
        sys.exit(f"[iv] the converter source is missing: {gtaweb}\n"
                 f"     Run: git submodule update --init   (see third_party/README.md)")
    exe = tools / f"whm2html{EXE}"
    sources = [p for p in gtaweb.iterdir() if p.suffix == ".go" or p.name in ("go.mod", "go.sum")]
    newest = max(p.stat().st_mtime for p in sources)
    if exe.exists() and not rebuild and exe.stat().st_mtime >= newest:
        return exe
    go, env = find_go(tools, force_pinned)
    ver = subprocess.run([str(go), "version"], capture_output=True, text=True, env=env).stdout.strip()
    log(f"  building whm2html with {ver}")
    tools.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(go), "build", "-trimpath", "-o", str(exe), "."], cwd=gtaweb, env=env)
    if r.returncode or not exe.exists():
        sys.exit("[iv] go build failed")
    return exe


# ------------------------------------------------------------------ steps

def ci_glob(folder: Path, pattern: str):
    """Case-insensitive glob in one folder (the game files keep their Windows spelling everywhere)."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and fnmatch.fnmatch(p.name.lower(), pattern))


def ci_path(base: Path, rel: str):
    """base/rel matching each component without regard to case (for installs on case-sensitive disks)."""
    p = base
    for part in Path(rel).parts:
        q = p / part
        if not q.exists() and p.is_dir():
            q = next((c for c in p.iterdir() if c.name.lower() == part.lower()), q)
        p = q
    return p


def export_textures(whm2html: Path, textures: Path, dest: Path):
    files = []
    for pat in TEXTURE_PATTERNS:
        files += [f for f in ci_glob(textures, pat) if f not in files]
    ok = bad = 0

    def one(f: Path):
        r = subprocess.run([str(whm2html), "wtd", str(f), str(dest / f.stem.lower())], capture_output=True, text=True)
        lines = (r.stdout + r.stderr).splitlines()
        return sum(1 for x in lines if x.strip() and "ERROR" not in x), sum(1 for x in lines if "ERROR" in x), r.returncode
    with ThreadPoolExecutor(max_workers=4) as pool:
        for good, errors, rc in pool.map(one, files):
            ok += good
            bad += errors + (1 if rc else 0)
    return len(files), ok, bad


def convert_pages(whm2html: Path, src: Path, dst: Path, american: Path):
    r = subprocess.run([str(whm2html), "iv", str(src), str(dst), str(american)], capture_output=True, text=True)
    out = r.stdout + r.stderr
    lines = out.splitlines()
    pages = sum(1 for x in lines if x.startswith("  -> ") and not re.fullmatch(r"  -> \d+ textures", x))
    errors = [x.strip() for x in lines if "ERROR" in x]
    if r.returncode:
        sys.exit(f"[iv] whm2html failed:\n{out[-2000:]}")
    return pages, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the GTA IV in-game internet from your own game files.")
    ap.add_argument("--config", help="config file (default: config.toml at the repository root)")
    ap.add_argument("--only", default="", help="comma-separated episodes to build: GTAIV,TLAD,TBoGT (default: all installed)")
    ap.add_argument("--keep", action="store_true", help="do not delete <out>/iv before building")
    ap.add_argument("--gtaweb", default=str(GTAWEB), help="converter source (default: third_party/gtaweb)")
    ap.add_argument("--pinned-go", action="store_true", help=f"always build with the pinned Go {GO_VERSION} (downloaded if needed)")
    ap.add_argument("--rebuild-converter", action="store_true", help="rebuild whm2html even if it is up to date")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    cfg = load_config(a.config)
    game = cfg.require("gta4")
    out = cfg.out / "iv"
    tools = cfg.tools
    gtaweb = Path(a.gtaweb).resolve()
    game_r = game.resolve()
    for p in (out, cfg.work):
        rp = p.resolve()
        if rp == game_r or game_r in rp.parents:
            sys.exit(f"[iv] {p} is inside the game folder; choose another out/work folder in the config.")
    if not (ci_path(game, "pc/html")).is_dir():
        sys.exit(f"[iv] {game} has no pc/html folder: point `gta4` at the folder that contains GTAIV.exe.")

    wanted = {x.strip().lower() for x in a.only.split(",") if x.strip()}
    episodes = []
    for name, sub in EPISODES:
        if wanted and name.lower() not in wanted:
            continue
        root = ci_path(game, sub) if sub else game
        html = ci_path(root, "pc/html")
        if not html.is_dir():
            log(f"[iv] {name}: not installed ({html}), skipped")
            continue
        episodes.append((name, root, html))
    if not episodes:
        sys.exit("[iv] nothing to build")
    if any(n != "GTAIV" for n, _, _ in episodes) and not any(n == "GTAIV" for n, _, _ in episodes) \
            and not (out / "GTAIV/pc/html").is_dir():
        log("[iv] note: the episodes reuse textures of the base game; build GTAIV too for complete pages")

    t0 = time.time()
    log(f"[iv] game:  {game}\n[iv] out:   {out}")
    whm2html = build_converter(tools, gtaweb, a.pinned_go, a.rebuild_converter)
    if out.exists() and not a.keep:
        if wanted:
            for name, _, _ in episodes:
                shutil.rmtree(out / name, ignore_errors=True)
        else:
            shutil.rmtree(out)
    base_gxt = ci_path(game, "common/text/american.gxt")
    font = gtaweb / "ttf" / "DIN-Medium.woff2"
    for name, root, html in episodes:
        dst = out / name / "pc" / "html"
        dst.mkdir(parents=True, exist_ok=True)
        # 1) page texts: the keys used by this episode's pages, from its GXT (base game as fallback)
        gxt = ci_path(root, "common/text/american.gxt")
        gxts = [gxt] + ([base_gxt] if name != "GTAIV" else [])
        american = out / name / "american.txt"
        n_str, n_keys, hits = gxt2txt.write_txt(gxts, html, american)
        # 2) shared textures
        n_dicts, n_tex, n_bad = export_textures(whm2html, ci_path(root, "pc/textures"), dst / "_tex")
        # 3) pages
        pages, errors = convert_pages(whm2html, html, dst, american)
        # 4) font
        if font.exists():
            (dst / "ttf").mkdir(exist_ok=True)
            shutil.copyfile(font, dst / "ttf" / font.name)
        log(f"[iv] {name}: {pages} pages, {n_tex} textures from {n_dicts} dictionaries"
            f"{f' ({n_bad} not decoded)' if n_bad else ''}, {hits} text keys"
            f"{f', {len(errors)} converter errors' if errors else ''}")
        for e in errors[:10]:
            log(f"       {e}")
    # 5) fill layer (after every episode: the episodes fall back to the base game's textures)
    log("[iv] fill layer")
    build_fill.build(game, out, log=log)
    n_files = sum(1 for p in out.rglob("*") if p.is_file())
    log(f"[iv] done in {time.time() - t0:.0f}s: {n_files} files in {out}")


if __name__ == "__main__":
    main()
