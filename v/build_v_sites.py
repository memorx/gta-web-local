#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_v_sites.py - the 81 GTA V story-mode in-game websites, rebuilt from YOUR game files.

    python v/build_v_sites.py                 every default stage (what is up to date is skipped)
    python v/build_v_sites.py --force         redo everything
    python v/build_v_sites.py --stages text,convert,pages
    python v/build_v_sites.py --only bawsaq,eyefind      (convert/pages of those sites only)

Paths come from config.toml at the repository root (common/config.py): cfg.gta5 is only read,
extracted and intermediate files go to <work>/v, downloaded tools to <work>/tools, and the
result to <out>/v (served at /v/; the pages load Ruffle from /_ruffle/ruffle.js).

Stages (default order; see docs/gta-v.md):
  tools      rage-cli, JPEXS FFDec, CodeWalker source and a .NET 8 SDK at pinned versions, and
             ytdexport (v/ytdexport) compiled against CodeWalker.Core          -> <work>/tools
  extract    the files the build needs, read from your install with rage-cli (v/extract.py):
             the 2013 sites (x64b.rpf), font libraries, GXT2 text, DLC text, the browser
             script appinternet.ysc (current + 2013) and the site textures (ytdexport + Pillow)
  update     current versions (update.rpf) of the 15 sites Rockstar republished, their
             textures, the dictionaries they load at run time and web_browser.gfx
  decompile  JPEXS ActionScript export of the sites (labels for the text tables; the 2013
             vehicle-site tables)
  scripts    data the browser script gives the sites, computed by running YOUR appinternet.ysc
             in a small VM (v/scriptdata): vehicle prices, eyefind news, bleeter pages, the
             Lifeinvader provider tables  -> host_data.json, www.lifeinvader.com.js
  text       strings_global.json / strings_web.json (v/gxt2json.py) and the Epsilon subtitles
  convert    <gfx> + its textures --v/gfx2swf.py-->  v/<domain>/site.swf (81 sites, in parallel).
             Sites with two versions: the current one in site.swf, the 2013 one in
             v/_lib/alt/<domain>/site.swf (?version=2013|actual)
  browser    web_browser (update.rpf) + its textures -> gfx2swf -> + host shim compiled with
             JPEXS (v/host) -> v/_lib/web_browser.swf
  lib        host.js, strings, host_data.json, the providers and gfxfontlib.swf -> v/_lib/
             (and Ruffle -> <out>/_ruffle/ if no other part of the build installed it)
  runtime    news_*, char_*, dyn_mp_*, dia_* dictionaries of scaleform_generic -> PNG
  tex        textures the sites request at run time (img://<txd>/<tex>) -> v/_tex/
  pages      v/<domain>/index.html = v/shell.html + configuration
  sites      v/_sites.json
  thumbs     index thumbnails from screenshots, if there are any (see shoot)
  index      v/index.html
Optional stage (never runs unless named in --stages):
  shoot      loads every site in Chrome (puppeteer-core, v/shoot/shoot.mjs) through a local
             server and takes a screenshot of each one for the index thumbnails (then run
             thumbs,index). Skipped cleanly when Node.js, puppeteer-core, Chrome or
             <out>/_ruffle/ruffle.js are missing. Example:
                 python v/build_v_sites.py --stages shoot,thumbs,index

Each page takes ?page=PAGE, ?version=2013|actual, ?personaje=michael|franklin|trevor and ?debug=1.
The ?v= stamps of the pages are content hashes: a rebuild with the same bytes keeps them.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

TOOLS_V = os.path.dirname(os.path.abspath(__file__))                 # <repo>/v
REPO = os.path.dirname(TOOLS_V)
sys.path.insert(0, REPO)
sys.path.insert(0, TOOLS_V)
from common.config import load_config  # noqa: E402

# ---------------------------------------------------------------------------
# Paths (set by configure() from config.toml)
# ---------------------------------------------------------------------------
CFG = None
GAME = ""        # GTA V install (read only)
WV = ""          # <work>/v
EXTRACT = ""     # <work>/v/extract (v/extract.py)
WORK = ""        # <work>/v/assemble
HOSTW = ""       # <work>/v/host (browser sources, compiled shim)
ASDIR = ""       # <work>/v/as (JPEXS ActionScript export)
SCRIPTDATA = ""  # <work>/v/scriptdata
TEXT = ""        # <work>/v/text
VDIR = LIB = TEX = ALT = ""
URL_V = "/v"
_TOOLS = None
_GAMEFILES = None


def configure(cfg) -> None:
    global CFG, GAME, WV, EXTRACT, WORK, HOSTW, ASDIR, SCRIPTDATA, TEXT, VDIR, LIB, TEX, ALT
    global UPDATE_RPF, UPDATE_SRC, UPDATE_TEX, RUNTIME_RPFS, RUNTIME_LOCAL
    CFG = cfg
    GAME = str(cfg.require("gta5")).replace("\\", "/")
    WV = os.path.join(str(cfg.work), "v")
    EXTRACT = os.path.join(WV, "extract")
    WORK = os.path.join(WV, "assemble")
    HOSTW = os.path.join(WV, "host")
    ASDIR = os.path.join(WV, "as")
    SCRIPTDATA = os.path.join(WV, "scriptdata")
    TEXT = os.path.join(WV, "text")
    VDIR = os.path.join(str(cfg.out), "v")
    LIB = os.path.join(VDIR, "_lib")
    TEX = os.path.join(VDIR, "_tex")
    ALT = os.path.join(LIB, "alt")
    UPDATE_RPF = GAME + "/update/update.rpf"
    UPDATE_SRC = os.path.join(WORK, "update_src", *UPDATE_WEB.split("/"))
    UPDATE_TEX = os.path.join(WORK, "update_tex")
    RUNTIME_RPFS = [  # order of application: the last one wins (update.rpf is the patch)
        ("base", GAME + "/x64b.rpf", "data/cdimages/scaleform_generic.rpf"),
        ("update", GAME + "/update/update.rpf", "x64/data/cdimages/scaleform_generic.rpf"),
    ]
    RUNTIME_LOCAL = {
        "base": os.path.join(EXTRACT, "gen_x64b", "data", "cdimages", "generic"),
        "update": os.path.join(EXTRACT, "gen_update", "x64", "data", "cdimages", "generic"),
    }


def tools():
    global _TOOLS
    if _TOOLS is None:
        from thirdparty import Tools
        _TOOLS = Tools(CFG)
    return _TOOLS


def gamefiles():
    global _GAMEFILES
    if _GAMEFILES is None:
        from extract import GameFiles
        _GAMEFILES = GameFiles(CFG, tools())
    return _GAMEFILES


# Texture dictionaries the sites request at run time that live in scaleform_generic.rpf
# (not in the sites' .ytd): eyefind news headers, bleeter avatars (CHAR_* and, for 8 story
# characters, DIA_*) and dynasty8 property photos. A scan of the strings of the 81 sites
# (2013 and current) and of appinternet.sc against every known .ytd found no other
# story-mode prefix (the rest is Online: mp_*, foreclosures_*).
# Adding a prefix here is enough: the runtime stage exports only the prefixes it lacks.
RUNTIME_PREFIXES = ("news_", "char_", "dyn_mp_", "dia_")
RUNTIME_RPFS: list = []
RUNTIME_LOCAL: dict = {}
# Prefixes of the first version of the cache (done.txt without done_prefixes.txt)
RUNTIME_PREFIXES_V1 = ("news_", "char_", "dyn_mp_")

# "Current" version of the sites: Rockstar republished 15 story-mode sites in update.rpf (what
# an Enhanced player sees today: e.g. SSASA with the photos of Dukes, Blista Compact and
# Stallion, which in the 2013 one are a placeholder Infernus). web_x64b has the 2013 one.
# Each site with both keeps one as default in v/<domain>/site.swf and the other in
# v/_lib/alt/<domain>/site.swf (?version=2013|actual).
UPDATE_RPF = ""
UPDATE_WEB = "x64/patch/data/cdimages/scaleform_web.rpf"
UPDATE_SRC = ""
UPDATE_TEX = ""
# Dictionaries those versions request at run time (vehicle and property photos), next to
# them in scaleform_web.rpf. Online ones left out (mp_*, foreclosures_*, casino_*...).
UPDATE_RUNTIME_PREFIXES = ("sssa_", "lgm_", "elt_", "dock_", "pandm_", "candc_", "dyn_", "dyn8_", "web_")
PREFER = "update"            # default version of the sites that have both
PREFER_SITE: dict = {}       # per-domain exceptions: {"www.x.com": "base"}
VERSION_LABEL = {"base": "2013", "update": "actual"}

STAGES = ["tools", "extract", "update", "decompile", "scripts", "text", "convert", "browser", "lib",
          "runtime", "tex", "pages", "sites", "thumbs", "index"]
OPTIONAL_STAGES = ["shoot"]
ORDER = ["tools", "extract", "update", "decompile", "scripts", "text", "convert", "browser", "lib",
         "runtime", "tex", "pages", "sites", "shoot", "thumbs", "index"]

# The six vehicle sites (their 2013 versions carry their own price tables)
VEHICLE_SITES = ("www_legendarymotorsport_net", "www_elitastravel_com", "www_warstock_d_cache_d_and_d_carry_com",
                 "www_docktease_com", "www_pandmcycles_com", "www_southernsanandreassuperautos_com")

# Character each site opens with (Michael by default). The banks only know their own
# customer (BANKS_baseclass.POPULATE_TEXT): Maze Bank = Michael, Fleeca = Franklin,
# Bank of Liberty = Trevor; with another character they say "Username Unrecognized", as in the game.
CHARACTER = {
    "www.fleeca.com": "franklin",
    "www.thebankofliberty.com": "trevor",
    # The C.o.M process is Franklin's: the site only accepts the passwords with browser.player == 2
    # (WWW_THECHILDRENOFTHEMOUNTAIN_COM.goToAnchor); providers/www.thechildrenofthemountain.com.js
    "www.thechildrenofthemountain.com": "franklin",
}

# What each site shows that does not come from your save game, and why (shown on the index;
# the web UI is in Spanish). Only things checked on screenshots or documented by the providers.
NOTES = {
    "www.lifeinvader.com": "Perfil y muro de Michael con la historia terminada (el juego usa tu partida); "
                           "?personaje=franklin o trevor abre el suyo.",
    "www.bawsaq.com": "Precios, gráficas y dinero inventados (en el juego venían de Rockstar en línea); "
                      "10 empresas con los precios de las capturas del juego. Las compras no se hacen.",
    "www.lcn-exchange.com": "Precios, gráficas y dinero inventados (en el juego los genera tu partida). "
                            "Las compras no se hacen.",
    "www.fleeca.com": "Se abre como Franklin, su cliente. Saldo y movimientos inventados; los conceptos son del juego.",
    "www.maze-bank.com": "Se abre como Michael, su cliente. Saldo y movimientos inventados; los conceptos son del juego.",
    "www.thebankofliberty.com": "Se abre como Trevor, su cliente. Saldo y movimientos inventados; los conceptos son del juego.",
    "www.epsilonprogram.com": "Con el hilo de Epsilon terminado: la presentación de Cris sale con subtítulos "
                              "(sin audio) y la túnica, agotada.",
    "www.eyefind.info": "Noticia, clima y zona salen al azar de toda la historia (el juego usa tu partida).",
    "www.bleeter.biz": "Muestra los bleets de todas las misiones (el juego solo los que llevas).",
    "www.thechildrenofthemountain.com": "Se abre como Franklin, con el proceso C.o.M sin empezar: los correos de "
                                        "Brother Adrian con las contraseñas salen bajo el visor; los cobros no se "
                                        "descuentan.",
}

# Sites that only exist in story mode (the rest also appear in GTA Online), and the six
# Online-only sites of the game that are left out (they are not in x64b.rpf).
STORY_ONLY = {
    "www.bawsaq.com", "www.bleeter.biz", "www.cashfordeaddreams.com", "www.dr-friedlander.com",
    "www.epsilonprogram.com", "www.hushsmush.com", "www.lcn-exchange.com", "www.lennyavery-realty.com",
    "www.lifeinvader.com", "www.thebankofliberty.com", "www.vinewoodloglinegenerator.com",
}
EXCLUDED_ONLINE = ["foreclosures.maze-bank.com", "www.arenawar.tv", "www.bennysoriginalmotorworks.com",
                   "www.dynasty8executiverealty.com", "www.prixluxuryrealestate.com",
                   "www.thediamondcasinoandresort.com"]


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_text(path: str, text: str) -> bool:
    """Write only if the content changes (dates and browser caches do not move for nothing)."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            if fh.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def copy_if_changed(src: str, dst: str) -> bool:
    """Copy src to dst unless dst already has the same bytes."""
    try:
        if os.path.getsize(src) == os.path.getsize(dst):
            with open(src, "rb") as a, open(dst, "rb") as b:
                if a.read() == b.read():
                    return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def short_hash(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def domain_of(gfx: str) -> str:
    """www_accept_d_the_d_chaos_com -> www.accept-the-chaos.com"""
    return gfx.replace("_d_", "-").replace("_", ".")


def sites_from_map(only: list | None) -> list:
    """The story-mode sites: every www_*.gfx of x64b.rpf's scaleform_web.rpf, by file name."""
    web = os.path.join(EXTRACT, "web_x64b")
    names = sorted(f[:-4] for f in os.listdir(web) if f.startswith("www_") and f.endswith(".gfx")) \
        if os.path.isdir(web) else []
    sites = [{"domain": domain_of(n), "gfx": n} for n in names]
    if only:
        sites = [s for s in sites if any(o in s["domain"] for o in only)]
    return sites


def require_sites() -> list:
    sites = sites_from_map(None)
    if len(sites) < 81:
        raise SystemExit("no sites in %s: run the extract stage first" % os.path.join(EXTRACT, "web_x64b"))
    return sites


# ---------------------------------------------------------------------------
# tools / extract
# ---------------------------------------------------------------------------
def stage_tools() -> None:
    tools().all()


def stage_extract(force: bool) -> None:
    gamefiles().run(None, force)


# ---------------------------------------------------------------------------
# convert: .gfx -> site.swf (gfx2swf.py, one process per core)
# ---------------------------------------------------------------------------
_FONTLIB = None


def _worker_init(extract_root: str) -> None:
    """Each process loads the game's font libraries once."""
    global _FONTLIB
    sys.path.insert(0, TOOLS_V)
    import gfx2swf  # noqa: E402
    _FONTLIB = gfx2swf.FontLibrary(extract_root)


def _convert_one(job: tuple) -> dict:
    import gfx2swf  # noqa: E402
    domain, variant, role, gfx, tex_dir, out, png_root, strings = job
    t0 = time.time()
    tmp = out + ".tmp"
    rec = {"domain": domain, "variant": variant, "role": role}
    try:
        st = gfx2swf.convert_file(gfx, tex_dir if os.path.isdir(tex_dir) else None, tmp, png_root,
                                  gfx2swf.Options(strings_paths=strings), _FONTLIB)
        os.replace(tmp, out)
        rec.update(ok=True, secs=round(time.time() - t0, 1), bytes=os.path.getsize(out),
                   images=st.images, imagesMissing=list(st.images_missing), fonts=st.fonts,
                   fontsInlined=len(st.fonts_inlined))
    except Exception as e:  # one broken site does not stop the others
        if os.path.exists(tmp):
            os.remove(tmp)
        rec.update(ok=False, error="%s: %s" % (type(e).__name__, e))
    return rec


def site_variants(s: dict) -> dict:
    """Sources of each available version of a site: {"base": (gfx, tex), "update": ...}."""
    v = {"base": (os.path.join(EXTRACT, "web_x64b", s["gfx"] + ".gfx"), os.path.join(EXTRACT, "png", s["gfx"]))}
    up = os.path.join(UPDATE_SRC, s["gfx"] + ".gfx")
    if os.path.exists(up):
        v["update"] = (up, os.path.join(UPDATE_TEX, "png", s["gfx"]))
    return v


def chosen_variants(s: dict) -> tuple:
    """(default version, alternative version or None) of a site."""
    v = site_variants(s)
    want = PREFER_SITE.get(s["domain"], PREFER)
    primary = want if want in v else "base"
    alt = next((k for k in v if k != primary), None)
    return primary, alt


def strings_paths() -> list:
    return [os.path.join(TEXT, "strings_web.json"), os.path.join(TEXT, "strings_global.json")]


def stage_convert(sites: list, force: bool, jobs: int) -> dict:
    for p in strings_paths():
        if not os.path.exists(p):
            raise SystemExit("convert: %s is missing (run the text stage)" % p)
    deps = [os.path.join(TOOLS_V, "gfx2swf.py")] + strings_paths()
    tool_mtime = max(os.path.getmtime(p) for p in deps)
    report_path = os.path.join(WORK, "convert_report.json")
    report = load_json(report_path, {}) or {}
    png_root = os.path.join(EXTRACT, "png")
    todo = []
    for s in sites:
        d = s["domain"]
        srcs = site_variants(s)
        primary, alt = chosen_variants(s)
        outs = [(primary, "primary", os.path.join(VDIR, d, "site.swf"))]
        if alt:
            outs.append((alt, "alt", os.path.join(ALT, d, "site.swf")))
        elif os.path.exists(os.path.join(ALT, d, "site.swf")):
            os.remove(os.path.join(ALT, d, "site.swf"))          # no other version any more
        for variant, role, out in outs:
            gfx, tex_dir = srcs[variant]
            newest_in = max(os.path.getmtime(gfx), tool_mtime,
                            os.path.getmtime(tex_dir) if os.path.isdir(tex_dir) else 0)
            prev = report.get(d if role == "primary" else d + "#alt", {})
            if (force or not os.path.exists(out) or os.path.getmtime(out) < newest_in
                    or prev.get("variant") != variant or not prev.get("ok")):
                os.makedirs(os.path.dirname(out), exist_ok=True)
                todo.append((d, variant, role, gfx, tex_dir, out, png_root, strings_paths()))
    log("convert: %d SWF to convert (%d sites)" % (len(todo), len(sites)))
    if todo:
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=max(1, jobs), initializer=_worker_init,
                                 initargs=(EXTRACT,)) as ex:
            futs = [ex.submit(_convert_one, j) for j in todo]
            for f in as_completed(futs):
                r = f.result()
                report[r["domain"] if r["role"] == "primary" else r["domain"] + "#alt"] = r
                tag = "%s/%s" % (r["variant"], r["role"])
                if r["ok"]:
                    log("  OK  %-42s %-14s %5.1fs %7d KB  imgs=%d missing=%d" % (
                        r["domain"], tag, r["secs"], r["bytes"] // 1024, r["images"], len(r["imagesMissing"])))
                else:
                    log("  ERR %-42s %-14s %s" % (r["domain"], tag, r["error"]))
        log("convert: %.0f s" % (time.time() - t0))
        os.makedirs(WORK, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
    bad = [d for d, r in report.items() if not r.get("ok")]
    if bad:
        log("convert: FAILED %s" % ", ".join(bad))
    return report


# ---------------------------------------------------------------------------
# DDS -> PNG (Pillow; A8/L8 are decoded by gfx2swf.load_dds)
# ---------------------------------------------------------------------------
def dds_to_png(src: str, dst: str) -> bool:
    import gfx2swf  # noqa: E402
    try:
        img = gfx2swf.load_dds(src)
    except Exception as e:
        log("  could not read %s: %s" % (src, e))
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    img.save(dst, optimize=True)
    return True


def ytd_export(ytd_or_dir: str, out_dir: str) -> bool:
    """ytdexport (CodeWalker.Core; gen9 on Enhanced) -> <out_dir>/<ytd>/<tex>.dds"""
    cmd = tools().ytdexport() + [ytd_or_dir, out_dir] + (["--gen9"] if gamefiles().gen9 else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("  ytdexport failed: %s" % (r.stderr or r.stdout).strip()[-400:])
        return False
    log("  " + (r.stdout.strip().splitlines() or ["ytdexport: ?"])[-1])
    return True


# ---------------------------------------------------------------------------
# browser: web_browser.swf with images + fonts + host shim
# ---------------------------------------------------------------------------
def stage_browser(force: bool) -> str:
    out = os.path.join(LIB, "web_browser.swf")
    src_gfx = os.path.join(HOSTW, "src", "web_browser_update.gfx")
    src_ytd = os.path.join(HOSTW, "src", "web_browser_update.ytd")
    if not os.path.exists(src_gfx):
        raise SystemExit("browser: %s is missing (run the update stage)" % src_gfx)
    shim_dir = os.path.join(TOOLS_V, "host")
    deps = [src_gfx, os.path.join(TOOLS_V, "gfx2swf.py")] + [os.path.join(shim_dir, f) for f in os.listdir(shim_dir)]
    if not force and os.path.exists(out) and os.path.getmtime(out) >= max(os.path.getmtime(p) for p in deps if os.path.exists(p)):
        log("browser: up to date")
        return "cached"
    os.makedirs(LIB, exist_ok=True)
    # 1) textures of the .ytd of the update version (the one Enhanced runs)
    tex_png = os.path.join(WORK, "browser_tex", "png", "web_browser_update")
    if not os.path.isdir(tex_png) and os.path.exists(src_ytd):
        dds_root = os.path.join(WORK, "browser_tex", "dds")
        if ytd_export(src_ytd, dds_root):
            dds_dir = os.path.join(dds_root, "web_browser_update")
            for fn in os.listdir(dds_dir) if os.path.isdir(dds_dir) else []:
                if fn.lower().endswith(".dds"):
                    dds_to_png(os.path.join(dds_dir, fn), os.path.join(tex_png, fn[:-4].lower() + ".png"))
    if not os.path.isdir(tex_png):
        tex_png = os.path.join(EXTRACT, "png", "web_browser")   # the 2013 one, same names
    # 2) gfx -> swf with images and fonts
    import gfx2swf  # noqa: E402
    mid = os.path.join(WORK, "web_browser_img.swf")
    st = gfx2swf.convert_file(src_gfx, tex_png, mid, os.path.join(EXTRACT, "png"),
                              gfx2swf.Options(strings_paths=strings_paths()), gfx2swf.FontLibrary(EXTRACT))
    log("browser: %d images (%d missing: %s), %d fonts" % (
        st.images, len(st.images_missing), ", ".join(st.images_missing[:6]), st.fonts))
    # 3) host shim (compiled with JPEXS)
    sys.path.insert(0, shim_dir)
    import build_host_swf  # noqa: E402
    build_host_swf.build(mid, out + ".tmp", os.path.join(HOSTW, "shim"), tools().ffdec_cmd())
    os.replace(out + ".tmp", out)
    return "built"


# ---------------------------------------------------------------------------
# decompile: JPEXS ActionScript export
# ---------------------------------------------------------------------------
def jpexs_export(files: dict, out_dir: str, force: bool) -> None:
    """ffdec -export script of {name: .gfx}; the result is <out_dir>/<name>.swf/scripts/..."""
    stamp = os.path.join(out_dir, "inputs.json")
    want = {n: short_hash(p) for n, p in sorted(files.items())}
    if not force and load_json(stamp) == want:
        log("decompile: %s up to date" % os.path.basename(out_dir))
        return
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    src = out_dir + "_in"
    if os.path.isdir(src):
        shutil.rmtree(src)
    os.makedirs(src)
    for n, p in files.items():               # JPEXS reads GFX; a folder input wants .swf names
        shutil.copyfile(p, os.path.join(src, n + ".swf"))
    t0 = time.time()
    r = subprocess.run(tools().ffdec_cmd() + ["-export", "script", out_dir, src], capture_output=True, text=True)
    shutil.rmtree(src)
    got = [n for n in files if os.path.isdir(os.path.join(out_dir, n + ".swf", "scripts"))]
    if r.returncode != 0 or len(got) != len(files):
        raise SystemExit("decompile: JPEXS exported %d of %d movies:\n%s" % (
            len(got), len(files), (r.stdout + r.stderr)[-2000:]))
    with open(stamp, "w", encoding="utf-8") as fh:
        json.dump(want, fh, indent=1)
    log("decompile: %d movies -> %s (%.0f s)" % (len(files), out_dir, time.time() - t0))


def stage_decompile(force: bool) -> None:
    sites = require_sites()
    current, old = {}, {}
    for s in sites:
        srcs = site_variants(s)
        primary, _alt = chosen_variants(s)
        current[s["gfx"]] = srcs[primary][0]
        if s["gfx"] in VEHICLE_SITES:
            old[s["gfx"]] = srcs["base"][0]
    browser = os.path.join(HOSTW, "src", "web_browser_update.gfx")
    if not os.path.exists(browser):
        raise SystemExit("decompile: %s is missing (run the update stage)" % browser)
    current["web_browser"] = browser
    jpexs_export(current, os.path.join(ASDIR, "current"), force)
    jpexs_export(old, os.path.join(ASDIR, "2013"), force)


# ---------------------------------------------------------------------------
# text and script data
# ---------------------------------------------------------------------------
def gxt_files() -> dict:
    """The GXT2 inputs of the text tables, in the order the game applies them."""
    base, patch = gamefiles().lang_dirs()
    base, patch = str(base), (str(patch) if patch else None)
    dlc = [str(p) for p in gamefiles().dlc_globals()]
    patch_global = [os.path.join(patch, "global.gxt2")] if patch and os.path.exists(os.path.join(patch, "global.gxt2")) else []
    nws = sorted(f for f in os.listdir(base) if f.lower().startswith("nws_") and f.lower().endswith(".gxt2"))
    nws_patch = sorted(f for f in os.listdir(patch) if f.lower().startswith("nws_") and f.lower().endswith(".gxt2")) \
        if patch else []
    return {
        "global": [os.path.join(base, "global.gxt2")] + dlc + patch_global,
        "web": ([os.path.join(base, f) for f in ("global.gxt2", "lfi_m.gxt2", "lfi_f.gxt2", "lfi_t.gxt2")]
                + [os.path.join(base, f) for f in nws] + [os.path.join(patch, f) for f in nws_patch]
                + dlc + patch_global),
        "dialogue": [os.path.join(base, "epswaud.gxt2")] + (
            [os.path.join(patch, "epswaud.gxt2")] if patch and os.path.exists(os.path.join(patch, "epswaud.gxt2")) else []),
        "base": base, "patch": patch,
    }


def text_global(force: bool) -> str:
    import gxt2json  # noqa: E402
    out = os.path.join(TEXT, "strings_global.json")
    files = gxt_files()["global"]
    if force or not os.path.exists(out) or os.path.getmtime(out) < max(os.path.getmtime(f) for f in files):
        log("text: strings_global.json: %d texts" % gxt2json.build_global(out, files))
    return out


def stage_scripts(force: bool) -> None:
    """host_data.json, vehicle_sites_2013.json and the Lifeinvader provider (v/scriptdata)."""
    sg = text_global(force)
    g = gxt_files()
    os.makedirs(SCRIPTDATA, exist_ok=True)
    cmd = [sys.executable, os.path.join(TOOLS_V, "scriptdata", "build.py"),
           "--ysc", str(gamefiles().script("current")),
           "--ysc-2013", str(gamefiles().script("x64b")),
           "--as-2013", os.path.join(ASDIR, "2013"),
           "--gxt", g["base"],
           "--strings-global", sg,
           "--provider-template", os.path.join(TOOLS_V, "providers", "www.lifeinvader.com.js"),
           "--out", SCRIPTDATA]
    if g["patch"]:
        cmd += ["--gxt-patch", g["patch"]]
    t0 = time.time()
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("scripts: v/scriptdata/build.py failed (%d)" % r.returncode)
    for f in ("host_data.json", "vehicle_sites_2013.json", "www.lifeinvader.com.js"):
        if not os.path.exists(os.path.join(SCRIPTDATA, f)):
            raise SystemExit("scripts: %s was not produced" % f)
    log("scripts: done in %.0f s" % (time.time() - t0))


def stage_text(force: bool) -> None:
    import gxt2json  # noqa: E402
    text_global(force)
    g = gxt_files()
    host_data = os.path.join(SCRIPTDATA, "host_data.json")
    if not os.path.exists(host_data):
        raise SystemExit("text: %s is missing (run the scripts stage)" % host_data)
    providers = os.path.join(TOOLS_V, "providers")
    labels = gxt2json.candidates([os.path.join(ASDIR, "current")], [str(gamefiles().script("current"))],
                                 [providers], host_data)
    n = gxt2json.build_web(os.path.join(TEXT, "strings_web.json"), g["web"], labels)
    log("text: strings_web.json: %d labels" % n)
    eps = os.path.join(providers, "www.epsilonprogram.com.js")
    want = gxt2json.provider_labels(eps, r"EPSW_VOICE\d+_\d+")
    n = gxt2json.export_labels(os.path.join(TEXT, "www.epsilonprogram.com.json"), g["dialogue"], want)
    log("text: Epsilon subtitles: %d of %d lines" % (n, len(want)))


# ---------------------------------------------------------------------------
# lib: host.js, text, script data, providers and the font library
# ---------------------------------------------------------------------------
def provider_sources() -> dict:
    """Published name -> source file: v/providers/* (the Lifeinvader one is only a template)
    plus what the build generates from the game (Lifeinvader tables, Epsilon subtitles)."""
    src_dir = os.path.join(TOOLS_V, "providers")
    files = {f: os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith(".js") or f == "index.json"}
    files["www.lifeinvader.com.js"] = os.path.join(SCRIPTDATA, "www.lifeinvader.com.js")
    files["www.epsilonprogram.com.json"] = os.path.join(TEXT, "www.epsilonprogram.com.json")
    for f, p in files.items():
        if not os.path.exists(p):
            raise SystemExit("lib: %s is missing (run the scripts and text stages)" % p)
    return files


def sync_providers(force: bool) -> None:
    """Providers -> v/_lib/providers/ (mirror, by content).

    The host reads providers/index.json and loads <domain>.js and its deps; it fetches them
    with cache: 'no-cache', so they carry no ?v= stamp. Whatever is not a provider any more
    is removed from the published copy (the folder belongs to this stage only)."""
    files = provider_sources()
    dst_dir = os.path.join(LIB, "providers")
    manifest = load_json(files["index.json"])
    listed = manifest.get("providers", manifest) if isinstance(manifest, dict) else None
    if not isinstance(listed, dict):
        raise SystemExit("lib: providers/index.json is not a valid JSON object")
    for dom, spec in listed.items():      # every listed site needs its file and deps
        if dom.startswith("_"):
            continue
        spec = spec or {}
        for f in list(spec.get("deps", [])) + [spec.get("file", dom + ".js")]:
            if f not in files:
                raise SystemExit("lib: providers/index.json asks for %s for %s and it does not exist" % (f, dom))
    os.makedirs(dst_dir, exist_ok=True)
    changed = [f for f, p in sorted(files.items()) if copy_if_changed(p, os.path.join(dst_dir, f)) or force]
    stale = [f for f in os.listdir(dst_dir) if (f.endswith(".js") or f.endswith(".json")) and f not in files]
    for f in stale:
        os.remove(os.path.join(dst_dir, f))
    log("lib: providers/ %d files (%d sites in index.json), %d copied%s" % (
        len(files), len([k for k in listed if not k.startswith("_")]), len(changed),
        (", %d removed: %s" % (len(stale), ", ".join(stale))) if stale else ""))


def stage_lib(force: bool) -> None:
    os.makedirs(LIB, exist_ok=True)
    # the pages load Ruffle from /_ruffle/ (normally installed by the classic build)
    tools().install_ruffle(CFG.out)
    pairs = [
        (os.path.join(TOOLS_V, "host.js"), "host.js"),
        (os.path.join(TEXT, "strings_web.json"), "strings.json"),
        (os.path.join(TEXT, "strings_global.json"), "strings_all.json"),
        (os.path.join(SCRIPTDATA, "host_data.json"), "host_data.json"),
    ]
    for src, name in pairs:
        if not os.path.exists(src):
            raise SystemExit("lib: %s is missing" % src)
        if copy_if_changed(src, os.path.join(LIB, name)):
            log("lib: %s" % name)
    sync_providers(force)
    # The converted sites embed their fonts; the library would only be used by a SWF that keeps
    # the ImportAssets2 of "gfxfontlib.swf" (host.js rewrites that URL to fontLib).
    fl = os.path.join(LIB, "gfxfontlib.swf")
    if force or not os.path.exists(fl):
        import gfx2swf  # noqa: E402
        gfx2swf.build_fontlib(gfx2swf.FontLibrary(EXTRACT), fl, True)
        log("lib: gfxfontlib.swf (the game's fonts by $alias)")


# ---------------------------------------------------------------------------
# runtime: dictionaries of scaleform_generic.rpf (news_*, char_*, dyn_mp_*, dia_*)
# ---------------------------------------------------------------------------
def rage(args: list, timeout: int = 1800) -> str:
    return gamefiles().rage(args, timeout)


def stage_runtime(force: bool) -> None:
    """RUNTIME_PREFIXES dictionaries of scaleform_generic (base and update) -> runtime/png/<ytd>/.

    Incremental by prefix: done_prefixes.txt records the exported ones (--force: all). The
    .ytd come from the extracted scaleform_generic folders (RUNTIME_LOCAL) or, without them,
    from the game RPFs with rage-cli. ytdexport -> DDS -> PNG; update wins over base."""
    rt = os.path.join(WORK, "runtime")
    png_root = os.path.join(rt, "png")
    done = os.path.join(rt, "done.txt")
    done_pfx = os.path.join(rt, "done_prefixes.txt")
    have: set = set()
    if not force:
        if os.path.exists(done_pfx):
            with open(done_pfx, encoding="utf-8") as fh:
                have = {line.strip() for line in fh if line.strip()}
        elif os.path.exists(done):
            have = set(RUNTIME_PREFIXES_V1)
    todo = tuple(p for p in RUNTIME_PREFIXES if p not in have)
    if not todo:
        log("runtime: cache up to date (%s)" % png_root)
        return
    log("runtime: prefixes to export: %s" % " ".join(p + "*" for p in todo))
    ytd_root = os.path.join(rt, "ytd")
    dds_root = os.path.join(rt, "dds")
    sel_root = os.path.join(ytd_root, "sel")      # only this pass's .ytd, by origin
    if os.path.isdir(sel_root):
        shutil.rmtree(sel_root)
    picked = {}
    for tag, rpf, inner_dir in RUNTIME_RPFS:
        local = RUNTIME_LOCAL.get(tag)
        if local and os.path.isdir(local):
            src, how = local, "extracted"
        else:
            if not os.path.exists(rpf):
                log("runtime: %s: no extracted copy nor RPF, skipped" % tag)
                continue
            names = []
            for prefix in todo:
                for line in rage(["search", rpf, prefix + "*.ytd"]).splitlines():
                    m = re.search(r"scaleform_generic\.rpf/([^/\s]+\.ytd)\s*$", line.strip(), re.I)
                    if m and m.group(1).lower().startswith(todo):
                        names.append(m.group(1))
            names = sorted(set(names))
            dst = os.path.join(ytd_root, tag)
            for i in range(0, len(names), 60):   # in batches (command-line length)
                rage(["extract", "-r", "-o", dst, rpf] + ["%s/%s" % (inner_dir, n) for n in names[i:i + 60]])
            src, how = os.path.join(ytd_root, tag, *inner_dir.split("/")), "rage-cli"
        files = sorted(f for f in os.listdir(src) if f.lower().endswith(".ytd") and f.lower().startswith(todo)) \
            if os.path.isdir(src) else []
        sel = os.path.join(sel_root, tag)
        for f in files:
            copy_if_changed(os.path.join(src, f), os.path.join(sel, f))
        picked[tag] = [f[:-4].lower() for f in files]
        log("runtime: %s (%s): %d dictionaries %s" % (tag, how, len(files), "/".join(p + "*" for p in todo)))
        if files:
            ytd_export(sel, os.path.join(dds_root, tag))
    n = 0
    for tag, _rpf, _inner in RUNTIME_RPFS:        # base first, update on top
        base = os.path.join(dds_root, tag)
        want = set(picked.get(tag, []))
        if not os.path.isdir(base):
            continue
        for ytd in os.listdir(base):
            d = os.path.join(base, ytd)
            if not os.path.isdir(d) or ytd.lower() not in want:
                continue
            for fn in os.listdir(d):
                if fn.lower().endswith(".dds"):
                    if dds_to_png(os.path.join(d, fn), os.path.join(png_root, ytd.lower(), fn[:-4].lower() + ".png")):
                        n += 1
    os.makedirs(rt, exist_ok=True)
    with open(done_pfx, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(have | set(todo))) + "\n")
    with open(done, "a" if have else "w", encoding="utf-8") as fh:
        fh.write("%d PNG %s (%s)\n" % (n, time.strftime("%Y-%m-%d %H:%M"), " ".join(todo)))
    log("runtime: %d textures -> %s" % (n, png_root))


# ---------------------------------------------------------------------------
# update: current version (update.rpf) of the sites Rockstar republished + web_browser
# ---------------------------------------------------------------------------
def export_dir_to_png(ytd_dir: str, dds_root: str, png_root: str) -> int:
    """ytdexport of a folder of .ytd and DDS -> PNG (<png_root>/<ytd>/<tex>.png, lower case)."""
    if not os.path.isdir(ytd_dir) or not ytd_export(ytd_dir, dds_root):
        return 0
    n = 0
    for ytd in os.listdir(dds_root):
        d = os.path.join(dds_root, ytd)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            dst = os.path.join(png_root, ytd.lower(), fn[:-4].lower() + ".png")
            if fn.lower().endswith(".dds") and not os.path.exists(dst):
                n += dds_to_png(os.path.join(d, fn), dst)
    return n


def stage_update(force: bool) -> None:
    listing = os.path.join(WORK, "update_web_list.txt")
    if force or not os.path.exists(listing):
        found = set()
        for pat in ("www_*.gfx", "*.ytd", "web_browser.gfx"):
            for line in rage(["search", UPDATE_RPF, pat]).splitlines():
                m = re.search(r"update\.rpf:update\.rpf/(%s/[^/\s]+)\s*$" % re.escape(UPDATE_WEB), line.strip(), re.I)
                if m:
                    found.add(m.group(1))
        os.makedirs(WORK, exist_ok=True)
        with open(listing, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(found)) + "\n")
    inner = [line.strip() for line in open(listing, encoding="utf-8") if line.strip()]
    story = {s["gfx"] for s in require_sites()}
    names = {p.rsplit("/", 1)[1] for p in inner}
    sites = sorted(n[:-4] for n in names if n.endswith(".gfx") and n[:-4] in story)
    # 1) .gfx + .ytd of every republished site, and the browser
    want = [UPDATE_WEB + "/" + n + ext for n in sites + ["web_browser"] for ext in (".gfx", ".ytd")
            if n + ext in names and not os.path.exists(os.path.join(UPDATE_SRC, n + ext))]
    if want:
        rage(["extract", "-r", "-o", os.path.join(WORK, "update_src"), UPDATE_RPF] + want)
    log("update: %d story-mode sites with a version in update.rpf" % len(sites))
    host_src = os.path.join(HOSTW, "src")
    for ext in (".gfx", ".ytd"):
        src = os.path.join(UPDATE_SRC, "web_browser" + ext)
        if os.path.exists(src):
            copy_if_changed(src, os.path.join(host_src, "web_browser_update" + ext))
    if not os.path.exists(os.path.join(host_src, "web_browser_update.gfx")):
        raise SystemExit("update: web_browser.gfx not found in %s/%s" % (UPDATE_RPF, UPDATE_WEB))
    # 2) their textures
    png = os.path.join(UPDATE_TEX, "png")
    if force or any(not os.path.isdir(os.path.join(png, n)) for n in sites if n + ".ytd" in names):
        sel = os.path.join(UPDATE_TEX, "ytd")          # the sites' dictionaries only (not the browser's)
        if os.path.isdir(sel):
            shutil.rmtree(sel)
        for n in sites:
            if os.path.exists(os.path.join(UPDATE_SRC, n + ".ytd")):
                copy_if_changed(os.path.join(UPDATE_SRC, n + ".ytd"), os.path.join(sel, n + ".ytd"))
        log("update: site textures: %d PNG" % export_dir_to_png(sel, os.path.join(UPDATE_TEX, "dds"), png))
    # 3) dictionaries they request at run time (vehicle/property photos)
    rt = os.path.join(WORK, "runtime")
    done = os.path.join(rt, "done_update_web.txt")
    if force or not os.path.exists(done):
        dicts = sorted(n for n in names if n.endswith(".ytd") and n.lower().startswith(UPDATE_RUNTIME_PREFIXES))
        ydir = os.path.join(rt, "ytd", "update_web")
        missing = [UPDATE_WEB + "/" + n for n in dicts if not os.path.exists(os.path.join(ydir, *UPDATE_WEB.split("/"), n))]
        for i in range(0, len(missing), 60):
            rage(["extract", "-r", "-o", ydir, UPDATE_RPF] + missing[i:i + 60])
        src = os.path.join(ydir, *UPDATE_WEB.split("/"))
        sel = os.path.join(rt, "ytd", "update_web_sel")
        os.makedirs(sel, exist_ok=True)
        for n in dicts:
            if os.path.exists(os.path.join(src, n)):
                copy_if_changed(os.path.join(src, n), os.path.join(sel, n))
        n = export_dir_to_png(sel, os.path.join(rt, "dds", "update_web_sel"), os.path.join(rt, "png"))
        os.makedirs(rt, exist_ok=True)
        with open(done, "w", encoding="utf-8") as fh:
            fh.write("%d dictionaries, %d PNG %s\n" % (len(dicts), n, time.strftime("%Y-%m-%d %H:%M")))
        log("update: %d run-time dictionaries -> %d PNG" % (len(dicts), n))


# ---------------------------------------------------------------------------
# tex: publish /v/_tex/<txd>/<tex>.png (lower case, as host.js asks)
# ---------------------------------------------------------------------------
def stage_tex() -> None:
    copied = total = 0
    png = os.path.join(EXTRACT, "png")
    dds = os.path.join(EXTRACT, "dds")
    sources = []
    for d in sorted(os.listdir(png)):
        if d.lower().startswith(("thumbnail_", "web_")) and d.lower() != "web_browser":
            sources.append((os.path.join(png, d), os.path.join(dds, d), d.lower()))
    rt = os.path.join(WORK, "runtime", "png")
    if os.path.isdir(rt):
        for d in sorted(os.listdir(rt)):
            sources.append((os.path.join(rt, d), None, d.lower()))
    for src_png, src_dds, txd in sources:
        names = {}
        if os.path.isdir(src_png):
            for fn in os.listdir(src_png):
                if fn.lower().endswith(".png"):
                    names[fn[:-4].lower()] = ("png", os.path.join(src_png, fn))
        # A8 textures without PNG: decoded from the DDS
        if src_dds and os.path.isdir(src_dds):
            for fn in os.listdir(src_dds):
                k = fn[:-4].lower()
                if fn.lower().endswith(".dds") and k not in names:
                    names[k] = ("dds", os.path.join(src_dds, fn))
        for k, (kind, src) in names.items():
            dst = os.path.join(TEX, txd, k + ".png")
            total += 1
            if kind == "png":
                copied += copy_if_changed(src, dst)
            elif not os.path.exists(dst):
                copied += dds_to_png(src, dst)
    log("tex: %d textures in %d dictionaries (%d copied now) -> %s" % (total, len(sources), copied, TEX))


# ---------------------------------------------------------------------------
# pages: index.html of every site = shell.html + configuration (the page UI is in Spanish)
# ---------------------------------------------------------------------------
SHELL_MARK = "<script>\n  // Punto de configuraci"


def shell_config(domain: str, stamp: dict, versions: dict) -> str:
    """window.GTAV_SHELL for /v/: everything in /v/_lib/, the site in /v/<domain>/site.swf."""
    return """<script>
  // Configuración de /v/ (generada por v/build_v_sites.py; no editar a mano).
  // La plantilla por defecto usaría /v/_host/ y el .swf Legacy sin imágenes.
  //
  // Personaje: en el juego el teléfono de cada uno es un "skin" del navegador
  // (SET_BROWSER_SKIN: 0 iFruit = Michael, 2 Badger = Franklin, 3 Facade = Trevor) y las
  // webs lo leen en browser.player; p. ej. cada banco solo reconoce a su cliente. Por
  // defecto se abre con el personaje que tiene sentido para la web; ?personaje=
  // michael|franklin|trevor lo cambia.
  var gtavQs = new URLSearchParams(location.search);
  var GTAV_PJ = { michael: [0, 0], franklin: [2, 1], trevor: [3, 2] };   // [skin, character]
  var gtavPjName = (gtavQs.get('personaje') || '').toLowerCase();
  if (!GTAV_PJ[gtavPjName]) gtavPjName = '';
  var gtavPj = GTAV_PJ[gtavPjName || %(pj)s];
  // Versiones: algunas webs están dos veces en el juego, la original de 2013 (x64b.rpf) y
  // la actual (update.rpf). ?version=2013|actual elige; sin parámetro, la de por defecto.
  var GTAV_VERSIONS = %(versions)s;   // dominio -> [por defecto, alternativa]
  var gtavVer = (gtavQs.get('version') || '').toLowerCase();
  function gtavUseAlt(domain) { var v = GTAV_VERSIONS[domain]; return !!(v && gtavVer === v[1]); }
  window.GTAV_SHELL = {
    domain: %(domain)s,
    ruffle: '/_ruffle/ruffle.js',
    host: '%(v)s/_lib/host.js?v=%(host)s',
    hostOptions: {
      base: '%(v)s',
      browserSwf: '%(v)s/_lib/web_browser.swf?v=%(browser)s',
      fontLib: '%(v)s/_lib/gfxfontlib.swf',
      stringsUrl: '%(v)s/_lib/strings.json?v=%(strings)s',
      stringsFallbackUrl: '%(v)s/_lib/strings_all.json?v=%(strings_all)s',
      dataUrl: '%(v)s/_lib/host_data.json?v=%(data)s',
      sitesUrl: '%(v)s/_sites.json',
      texBase: '%(v)s/_tex/',
      skin: gtavPj[0],
      character: gtavPj[1],
      // cada web convertida (imágenes y fuentes del juego dentro) vive en su carpeta; la
      // otra versión (si la hay) en _lib/alt/
      siteSwf: function (id, domain) {
        return (gtavUseAlt(domain) ? '%(v)s/_lib/alt/' : '%(v)s/') + domain + '/site.swf?v=%(sites)s';
      },
      // al navegar dentro del navegador del juego la dirección conserva versión y personaje
      pageUrl: function (domain, page) {
        var q = [];
        if (page && page !== 'PAGE1') q.push('page=' + encodeURIComponent(page));
        if (gtavVer) q.push('version=' + encodeURIComponent(gtavVer));
        if (gtavPjName) q.push('personaje=' + encodeURIComponent(gtavPjName));
        return '%(v)s/' + domain + '/index.html' + (q.length ? '?' + q.join('&') : '');
      },
    },
    gallery: '%(v)s/{domain}/gallery.html',
    index: '%(v)s/',
  };

  // Enlace a la otra versión en la barra (solo en las webs que tienen dos)
  document.addEventListener('DOMContentLoaded', function () {
    var tools = document.querySelector('.tools');
    if (!tools) return;
    var a = document.createElement('a');
    a.id = 'versionLink';
    a.hidden = true;
    tools.insertBefore(a, tools.firstChild);
    function update(domain) {
      var v = GTAV_VERSIONS[domain];
      if (!v) { a.hidden = true; return; }
      var showing = gtavUseAlt(domain) ? v[1] : v[0];
      var other = showing === v[0] ? v[1] : v[0];
      a.hidden = false;
      a.textContent = other === '2013' ? 'Versión de 2013' : 'Versión actual';
      a.title = 'Esta web tiene dos versiones en los archivos del juego; ahora ves la '
        + (showing === '2013' ? 'original de 2013' : 'actual (update.rpf)');
      a.href = '%(v)s/' + domain + '/index.html' + (other === v[0] ? '' : '?version=' + other);
    }
    update(window.GTAV_SHELL.domain);
    (function hook() {
      if (window.gtavHost) window.gtavHost.on('navigate', function (i) { update(i.domain); });
      else setTimeout(hook, 200);
    })();
  });
</script>
""" % dict(stamp, domain=json.dumps(domain), v=URL_V, pj=json.dumps(CHARACTER.get(domain, "michael")),
           versions=json.dumps(versions, separators=(",", ":")))


def version_map() -> dict:
    """domain -> [default label, alternative label] of the sites with two versions."""
    out = {}
    for s in sites_from_map(None):
        primary, alt = chosen_variants(s)
        if alt and os.path.exists(os.path.join(ALT, s["domain"], "site.swf")):
            out[s["domain"]] = [VERSION_LABEL[primary], VERSION_LABEL[alt]]
    return out


def stage_pages(sites: list, only: bool) -> None:
    template = open(os.path.join(TOOLS_V, "shell.html"), encoding="utf-8").read()
    if SHELL_MARK not in template:
        raise SystemExit("pages: shell.html changed; the configuration block was not found")
    lib = lambda n: os.path.join(LIB, n)  # noqa: E731
    # version stamp so that browsers do not use stale cached copies. By CONTENT (relative
    # path + sha1 of every site.swf), not by date: a convert --force with the same bytes
    # keeps the same stamp.
    all_swf = hashlib.sha1()
    for s in sorted(sites_from_map(None), key=lambda x: x["domain"]):
        for p in (os.path.join(VDIR, s["domain"], "site.swf"), os.path.join(ALT, s["domain"], "site.swf")):
            if os.path.exists(p):
                rel = os.path.relpath(p, VDIR).replace(os.sep, "/")
                all_swf.update(("%s:%s\n" % (rel, short_hash(p))).encode())
    stamp = {
        "host": short_hash(lib("host.js")), "browser": short_hash(lib("web_browser.swf")),
        "strings": short_hash(lib("strings.json")), "strings_all": short_hash(lib("strings_all.json")),
        "data": short_hash(lib("host_data.json")), "sites": all_swf.hexdigest()[:10],
    }
    versions = version_map()
    n = 0
    for s in sites:
        d = s["domain"]
        name = d[4:] if d.startswith("www.") else d
        page = template.replace(SHELL_MARK, shell_config(d, stamp, versions) + SHELL_MARK, 1)
        page = page.replace("<title>GTA V · navegador</title>", "<title>%s · GTA V</title>" % html.escape(name), 1)
        n += write_text(os.path.join(VDIR, d, "index.html"), page)
    log("pages: %d index.html written (%d up to date)" % (n, len(sites) - n))


# ---------------------------------------------------------------------------
# sites: _sites.json
# ---------------------------------------------------------------------------
def stage_sites(convert_report: dict) -> dict:
    """v/_sites.json: the sites with their mode, notes and versions (read by host.js and the shell).
    "shots" (screenshots of a gallery page) is always 0: this build has no gallery, so the
    shell keeps its gallery link hidden."""
    path = os.path.join(VDIR, "_sites.json")
    versions = version_map()
    story = []
    for s in require_sites():
        d = s["domain"]
        e = {"domain": d, "mode": "story" if d in STORY_ONLY else "both", "shots": 0}
        e["built"] = os.path.exists(os.path.join(VDIR, d, "site.swf"))
        if e["built"]:
            e["swf"] = "site.swf"
        if d in NOTES:
            e["note"] = NOTES[d]
        if d in versions:          # [default, alternative]: "actual" / "2013"
            e["versions"] = versions[d]
        story.append(e)
    data = {"story": story, "excludedOnline": EXCLUDED_ONLINE}
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if write_text(path, text):
        log("sites: _sites.json written (%d sites, %d built)" % (len(story), sum(1 for s in story if s["built"])))
    return data


# ---------------------------------------------------------------------------
# shoot (optional): screenshots for the thumbnails, with Chrome + puppeteer-core
# ---------------------------------------------------------------------------
def _static_server(root: str):
    """A throw-away HTTP server for <out> on a free local port (/v/ and /_ruffle/ as the real
    server maps them). Returns (server, base URL of /v)."""
    import functools
    import http.server
    import threading

    class Quiet(http.server.SimpleHTTPRequestHandler):
        extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{
            ".wasm": "application/wasm", ".js": "text/javascript", ".mjs": "text/javascript",
            ".json": "application/json", ".swf": "application/x-shockwave-flash"})

        def log_message(self, *args):  # noqa: D401 - silence the access log
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=root))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/v" % srv.server_address[1]


def stage_shoot(shots_dir: str, only: list) -> None:
    """node v/shoot/shoot.mjs against a local server of <out>: one screenshot per site in
    <shots_dir> (window) and <shots_dir>/viewport (the site only: what thumbs uses)."""
    script = os.path.join(TOOLS_V, "shoot", "shoot.mjs")
    node = shutil.which("node")
    if not node:
        log("shoot: skipped (Node.js is not on PATH)")
        return
    if not os.path.exists(os.path.join(str(CFG.out), "_ruffle", "ruffle.js")):
        log("shoot: skipped (%s is missing: build Ruffle first, see the main README)"
            % os.path.join(str(CFG.out), "_ruffle", "ruffle.js"))
        return
    if not os.path.exists(os.path.join(VDIR, "_sites.json")):
        log("shoot: skipped (%s is missing: run the default stages first)" % os.path.join(VDIR, "_sites.json"))
        return
    probe = subprocess.run([node, "-e", "import('puppeteer-core').then(()=>0,()=>process.exit(1))"],
                           cwd=os.path.dirname(script), capture_output=True, text=True)
    if probe.returncode != 0:
        log("shoot: skipped (puppeteer-core not found: run 'npm install' at the repository root)")
        return
    srv, base = _static_server(str(CFG.out))
    try:
        cmd = [node, script, "--base", base, "--out", shots_dir, "--jobs", str(SHOOT_JOBS)]
        if only:
            cmd += ["--only", ",".join(only)]
        log("shoot: %s" % base)
        r = subprocess.run(cmd)
    finally:
        srv.shutdown()
    if r.returncode == 3:
        log("shoot: skipped (no Chrome/Chromium/Edge found; set CHROME_PATH)")
    elif r.returncode != 0:
        log("shoot: some sites did not load (see %s); the thumbnails keep what they had"
            % os.path.join(shots_dir, "manifest.json"))


SHOOT_JOBS = 3


# ---------------------------------------------------------------------------
# thumbs: index thumbnails from the screenshots
# ---------------------------------------------------------------------------
def stage_thumbs(shots_dir: str) -> None:
    from PIL import Image
    out_dir = os.path.join(LIB, "thumbs")
    n = 0
    if not os.path.isdir(shots_dir):
        log("thumbs: no screenshots in %s (optional: --stages shoot,thumbs,index)" % shots_dir)
        return
    for fn in sorted(os.listdir(shots_dir)):
        if not (fn.startswith("www.") and fn.endswith(".png")):
            continue
        src = os.path.join(shots_dir, fn)
        dst = os.path.join(out_dir, fn[:-4] + ".jpg")
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue
        img = Image.open(src).convert("RGB")
        img.thumbnail((640, 640 * img.height // max(1, img.width)), Image.LANCZOS)
        os.makedirs(out_dir, exist_ok=True)
        img.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
        n += 1
    log("thumbs: %d new thumbnails -> %s" % (n, out_dir))


# ---------------------------------------------------------------------------
# index: /v/index.html (in Spanish, like the rest of the web UI)
# ---------------------------------------------------------------------------
INDEX = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GTA V Web</title>
<meta name="description" content="Las 81 webs del navegador de GTA V (modo historia), sacadas de los archivos del juego y reproducidas con Ruffle.">
<meta name="color-scheme" content="dark light">
<!-- Generado por v/build_v_sites.py -->
<style>
:root{--bg:#0e1014;--card:#171a21;--line:#272c37;--fg:#e9ebf1;--mut:#8b92a4;--acc:#f2b233;--field:#0e1014;--note:#e0784a}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f5f8;--card:#fff;--line:#e2e5ec;--fg:#15171c;--mut:#5d6474;--acc:#b87700;--field:#fff;--note:#c2511f}}
:root[data-theme="dark"]{--bg:#0e1014;--card:#171a21;--line:#272c37;--fg:#e9ebf1;--mut:#8b92a4;--acc:#f2b233;--field:#0e1014;--note:#e0784a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:auto;padding:28px 16px 60px}
a{color:var(--acc)}
h1{margin:6px 0}
.sub{color:var(--mut);max-width:780px;margin:6px 0 0}
.tools{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;margin-top:18px}
.tools input{flex:1 1 240px;max-width:360px;height:36px;border:1px solid var(--line);border-radius:18px;background:var(--field);
  color:var(--fg);padding:0 14px;font:inherit;font-size:14px}
.tools input:focus-visible{outline:2px solid var(--acc);outline-offset:1px}
.count{color:var(--mut);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-top:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.card[hidden]{display:none}
.card a.main{display:block;text-decoration:none;color:inherit}
.card a.main:hover .t,.card a.main:focus-visible .t{color:var(--acc)}
.card a.main:focus-visible{outline:2px solid var(--acc);outline-offset:-2px}
.thumb{aspect-ratio:1280/627;background:#000 center top/cover no-repeat}
.in{padding:10px 12px 0}
.t{font-weight:600;word-break:break-all}
.d{color:var(--mut);font-size:12px;margin-top:3px}
.n{color:var(--note);font-size:12px;margin-top:6px}
.alt{padding:8px 12px 10px;font-size:12px;margin-top:auto;display:flex;gap:12px;flex-wrap:wrap}
.foot{color:var(--mut);font-size:13px;margin-top:28px;max-width:780px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
</style></head><body><div class="wrap">
<a href="/">&larr; GTA Web Local</a>
<h1>GTA V: internet del modo historia</h1>
<p class="sub">__SUB__</p>
<div class="tools"><label class="sr" for="q">Buscar sitio</label>
<input id="q" type="search" placeholder="Buscar sitio…" autocomplete="off" spellcheck="false"><span class="count" id="count" aria-live="polite"></span></div>
<div class="grid" id="grid">__CARDS__</div>
<p class="foot">__FOOT__</p>
</div>
<script>
(function(){
  var q=document.getElementById('q'),cards=[].slice.call(document.querySelectorAll('.card')),c=document.getElementById('count');
  function f(){var v=q.value.trim().toLowerCase(),n=0;cards.forEach(function(e){var ok=!v||e.getAttribute('data-k').indexOf(v)>=0;e.hidden=!ok;if(ok)n++;});
    c.textContent=v?n+' de '+cards.length:cards.length+' sitios';}
  q.addEventListener('input',f);f();
})();
</script>
</body></html>
"""


def stage_index(data: dict) -> None:
    thumbs = os.path.join(LIB, "thumbs")
    versions = version_map()
    cards = []
    story = sorted(data["story"], key=lambda x: x["domain"].replace("www.", ""))
    for s in story:
        dom = s["domain"]
        name = dom.replace("www.", "")
        # thumbnail: screenshot of the converted site (shoot + thumbs) -> eyefind thumbnail
        thumb = ""
        if os.path.exists(os.path.join(thumbs, dom + ".jpg")):
            thumb = "_lib/thumbs/%s.jpg?v=%s" % (dom, short_hash(os.path.join(thumbs, dom + ".jpg")))
        if not thumb:
            tid = "thumbnail_" + re.sub(r"^www_", "", dom.replace("-", "_d_").replace(".", "_"))
            if os.path.exists(os.path.join(TEX, tid, tid + ".png")):
                thumb = "_tex/%s/%s.png" % (tid, tid)
        style = ' style="background-image:url(\'%s\')"' % html.escape(thumb) if thumb else ""
        mode = "solo historia" if s.get("mode") == "story" else "historia y Online"
        main = "%s/index.html" % dom
        note = '<div class="n">%s</div>' % html.escape(s["note"]) if s.get("note") else ""
        alt = []
        if dom in versions:
            other = versions[dom][1]
            alt.append('<a href="%s/index.html?version=%s">%s</a>' % (
                dom, other, "Versión de 2013" if other == "2013" else "Versión actual"))
        alt = '<div class="alt">%s</div>' % "".join(alt) if alt else '<div class="alt"></div>'
        cards.append(
            '<div class="card" data-k="%s"><a class="main" href="%s"><div class="thumb"%s role="img" aria-label="%s"></div>'
            '<div class="in"><div class="t">%s</div><div class="d">%s</div>%s</div></a>%s</div>'
            % (html.escape(name), main, style, html.escape("Captura de " + name), html.escape(name), mode, note, alt))
    built = sum(1 for s in story if s.get("built"))
    with_shots = sum(1 for s in story if s.get("shots"))
    sub = ("%d sitios del navegador del juego, sin los %d exclusivos de GTA Online. Cada tarjeta abre la página "
           "tal como la trae GTA V: el archivo Flash del juego (Scaleform) convertido para Ruffle, con sus imágenes y "
           "fuentes originales, dentro del navegador del teléfono. Los textos salen de los archivos de idioma del juego."
           % (len(story), len(data.get("excludedOnline", []))))
    if with_shots:
        sub += " %d sitios tienen además una galería de capturas." % with_shots
    if built < len(story):
        sub += " %d no se pudieron convertir (ver convert_report.json)." % (len(story) - built)
    foot = ("Los enlaces entre sitios funcionan como en el juego; la barra de arriba de cada página tiene atrás, adelante, "
            "inicio (eyefind.info) y la dirección. Lo que en el juego depende de tu partida (noticias, bolsa, saldos, "
            "perfiles) se simula o queda vacío, y las compras no se hacen. Todo es de Rockstar Games y se ve solo en esta PC.")
    page = INDEX.replace("__SUB__", html.escape(sub)).replace("__FOOT__", html.escape(foot)).replace("__CARDS__", "".join(cards))
    if write_text(os.path.join(VDIR, "index.html"), page):
        log("index: v/index.html written (%d cards)" % len(cards))
    else:
        log("index: up to date")


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    global PREFER
    ap = argparse.ArgumentParser(
        description="Build /v/: the GTA V story-mode in-game websites, from your own game files.",
        epilog="Default stages: %s. Optional stages (only when named): %s. See docs/gta-v.md." % (
            ", ".join(STAGES), ", ".join(OPTIONAL_STAGES)))
    ap.add_argument("--config", help="config.toml to use (default: the one at the repository root)")
    ap.add_argument("--stages", default=",".join(STAGES), help="comma-separated stages to run")
    ap.add_argument("--only", default="", help="filter sites by text in the domain (a,b,c) for convert, pages and shoot")
    ap.add_argument("--force", action="store_true", help="redo the stages even if they are up to date")
    ap.add_argument("--jobs", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)),
                    help="parallel conversions (default: %(default)s)")
    ap.add_argument("--shots", default=None, help="screenshot folder for thumbs (default: <work>/v/shots/viewport)")
    ap.add_argument("--prefer", choices=("base", "update"), default=None,
                    help="default version of the sites that have two (default: %s)" % PREFER)
    a = ap.parse_args(argv)
    configure(load_config(a.config))
    stages = [s.strip() for s in a.stages.split(",") if s.strip()]
    unknown = set(stages) - set(STAGES) - set(OPTIONAL_STAGES)
    if unknown:
        ap.error("unknown stages: %s" % ", ".join(sorted(unknown)))
    only = [o for o in a.only.split(",") if o]
    shots = a.shots or os.path.join(WV, "shots", "viewport")
    if a.prefer:
        PREFER = a.prefer
    os.makedirs(WORK, exist_ok=True)
    t0 = time.time()
    report = load_json(os.path.join(WORK, "convert_report.json"), {}) or {}
    data = None
    for stage in [s for s in ORDER if s in stages]:
        log("== %s" % stage)
        if stage == "tools":
            stage_tools()
        elif stage == "extract":
            stage_extract(a.force)
        elif stage == "update":
            stage_update(a.force)
        elif stage == "decompile":
            stage_decompile(a.force)
        elif stage == "scripts":
            stage_scripts(a.force)
        elif stage == "text":
            stage_text(a.force)
        elif stage == "convert":
            report = stage_convert(sites_from_map(only or None), a.force, a.jobs)
        elif stage == "browser":
            stage_browser(a.force)
        elif stage == "lib":
            stage_lib(a.force)
        elif stage == "runtime":
            stage_runtime(a.force)
        elif stage == "tex":
            stage_tex()
        elif stage == "pages":
            stage_pages(sites_from_map(only or None), bool(only))
        elif stage == "sites":
            data = stage_sites(report)
        elif stage == "shoot":
            stage_shoot(os.path.join(WV, "shots"), only)
        elif stage == "thumbs":
            stage_thumbs(shots)
        elif stage == "index":
            stage_index(data or load_json(os.path.join(VDIR, "_sites.json")) or stage_sites(report))
    log("done in %.0f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
