"""Extract from your GTA V install the files the GTA V build needs (read only on the game).

Everything lands in <work>/v/extract (cfg.work), with the archive layout kept:

  web_x64b/                   the 81 story-mode sites + web_browser (.gfx + .ytd), 2013 version
                              (x64b.rpf/data/cdimages/scaleform_web.rpf)
  gen_x64b/.../generic/       scaleform_generic.rpf of x64b.rpf and of update/update.rpf: font
  gen_update/.../generic/     libraries, eyefind thumbnails (thumbnail_*), shared web_* textures,
                              and the dictionaries the sites ask for at run time (news_, char_...)
  common/data/scaleform/      gfxfontlib.gfx (common.rpf)
  upd_ui/common/data/ui/,     fontmap.xml: the font aliases ("$Font2" -> family) of update.rpf
  common/data/ui/             and of common.rpf (the update.rpf copy wins)
  lang_update2/, lang_update/ american_rel GXT2 text: update2.rpf and the patch in update.rpf
  dlc_text/<pack>/...         global.gxt2 of every DLC pack (names of vehicles added later)
  scripts/current/...         appinternet.ysc of the current game (update2.rpf on Enhanced,
                              update.rpf on Legacy): the browser script whose data the sites show
  scripts/x64b/...            appinternet.ysc of 2013 (x64b.rpf), for the ?version=2013 sites
  dds/, png/                  the textures of the site dictionaries (ytdexport + Pillow)

rage-cli reads the archive keys from your own game executable (GTA5_Enhanced.exe or GTA5.exe).
Each step writes a marker file and is skipped next time (--force redoes them).

    python v/extract.py [--force] [--steps web,generic,fontlib,lang,dlc,scripts,textures]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from common.config import load_config  # noqa: E402
from thirdparty import Tools  # noqa: E402

STEPS = ["web", "generic", "fontlib", "lang", "dlc", "scripts", "textures"]
SCRIPT_INNER = {  # archive (relative to the game folder) -> path of appinternet.ysc inside it
    "update/update2.rpf": "x64/levels/gta5/script/script_rel.rpf/appinternet.ysc",
    "update/update.rpf": "x64/levels/gta5/script/script_rel.rpf/appinternet.ysc",
}
SCRIPT_2013 = ("x64b.rpf", "levels/gta5/script/script_rel.rpf/appinternet.ysc")


def log(msg: str) -> None:
    print("[extract] " + msg, flush=True)


class GameFiles:
    def __init__(self, cfg=None, tools: Tools | None = None):
        self.cfg = cfg or load_config()
        self.game = self.cfg.require("gta5")
        self.tools = tools or Tools(self.cfg)
        self.root = Path(self.cfg.work) / "v" / "extract"
        exe = self.game / "GTA5_Enhanced.exe"
        self.edition = "enhanced" if exe.exists() else "legacy"
        if not exe.exists():
            exe = self.game / "GTA5.exe"
        if not exe.exists():
            sys.exit("[extract] %s has neither GTA5_Enhanced.exe nor GTA5.exe; is gta5 in config.toml "
                     "the folder that contains x64b.rpf?" % self.game)
        self.exe = exe
        if not (self.game / "x64b.rpf").exists():
            sys.exit("[extract] %s has no x64b.rpf" % self.game)

    # ---- helpers ----------------------------------------------------------------
    @property
    def gen9(self) -> bool:
        """Enhanced textures are gen9 resources (ytdexport --gen9)."""
        return self.edition == "enhanced"

    def rage(self, args: list, timeout: int = 3600) -> str:
        cmd = [str(self.tools.rage())] + [str(a) for a in args]
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.tools.rage_env(self.exe),
                           timeout=timeout, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            log("rage-cli %s failed (%d): %s" % (" ".join(map(str, args[:3])), r.returncode, out.strip()[-600:]))
        return out

    def marker(self, step: str) -> Path:
        return self.root / (".done-" + step)

    def run(self, steps=None, force: bool = False) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        log("game: %s (%s edition)" % (self.game, self.edition))
        for step in steps or STEPS:
            m = self.marker(step)
            if m.exists() and not force:
                continue
            t0 = time.time()
            getattr(self, "step_" + step)()
            m.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            log("%s: done in %.0f s" % (step, time.time() - t0))

    def extract_nested(self, archive: Path, pattern: str, out: Path) -> list:
        """Extract the entries matching pattern (nested .rpf files come out as files)."""
        self.rage(["extract", archive, pattern, "-o", out])
        name = pattern.rsplit("/", 1)[-1].lstrip("*")
        return sorted(p for p in out.rglob("*") if p.is_file() and p.name.lower().endswith(name.lower()))

    # ---- steps --------------------------------------------------------------------
    def step_web(self) -> None:
        """The 2013 sites: x64b.rpf/data/cdimages/scaleform_web.rpf -> web_x64b/."""
        rpfs = self.extract_nested(self.game / "x64b.rpf", "*scaleform_web.rpf", self.root / "x64b")
        if not rpfs:
            sys.exit("[extract] scaleform_web.rpf not found in x64b.rpf")
        self.rage(["extract", rpfs[0], "*", "-o", self.root / "web_x64b"])
        n = len(list((self.root / "web_x64b").glob("www_*.gfx")))
        log("web: %d www_*.gfx" % n)
        if n < 81:
            sys.exit("[extract] expected the 81 story-mode sites in scaleform_web.rpf, found %d" % n)

    def step_generic(self) -> None:
        """scaleform_generic.rpf of x64b.rpf and update/update.rpf -> gen_<archive>/.../generic/."""
        for rel in ("x64b.rpf", "update/update.rpf"):
            src = self.game / rel
            dst = self.root / ("gen_" + Path(rel).stem)
            for rpf in self.extract_nested(src, "*scaleform_generic.rpf", dst):
                self.rage(["extract", rpf, "*", "-o", rpf.parent / "generic"])
                log("generic: %s -> %d files" % (rpf.relative_to(self.root),
                                                 len(list((rpf.parent / "generic").iterdir()))))

    def step_fontlib(self) -> None:
        """gfxfontlib.gfx and fontmap.xml (font aliases: "$Font2" -> family; the update.rpf copy wins)."""
        self.extract_nested(self.game / "common.rpf", "*gfxfontlib.gfx", self.root / "common")
        self.rage(["extract", "-o", self.root / "common", self.game / "common.rpf", "data/ui/fontmap.xml"])
        upd = self.game / "update" / "update.rpf"
        if upd.exists():
            self.rage(["extract", "-o", self.root / "upd_ui", upd, "common/data/ui/fontmap.xml"])
        found = [p for p in (self.root / "upd_ui" / "common/data/ui/fontmap.xml",
                             self.root / "common" / "data/ui/fontmap.xml") if p.exists()]
        if not found:
            sys.exit("[extract] fontmap.xml not found in update.rpf / common.rpf")
        log("fontlib: fontmap.xml from %s" % found[0].relative_to(self.root))

    def step_lang(self) -> None:
        """American English text: update2.rpf (base) and update.rpf (patch)."""
        for rel in ("update/update2.rpf", "update/update.rpf"):
            src = self.game / rel
            if not src.exists():
                continue
            for rpf in self.extract_nested(src, "*lang/american_rel.rpf", self.root / ("lang_" + src.stem)):
                self.rage(["extract", rpf, "*", "-o", rpf.parent / "american_rel"])
                log("lang: %s -> %d .gxt2" % (rpf.relative_to(self.root),
                                              len(list((rpf.parent / "american_rel").glob("*.gxt2")))))

    def step_dlc(self) -> None:
        """global.gxt2 of each DLC pack (update/x64/dlcpacks/<pack>/dlc.rpf)."""
        rx = re.compile(r"dlcpacks[\\/]([^\\/]+)[\\/]dlc\.rpf:dlc\.rpf/(x64/.*american[^/]*\.rpf/global\.gxt2)", re.I)
        listing = self.rage(["search", self.game / "update", "*american*/global.gxt2"], timeout=7200)
        packs: dict = {}
        for line in listing.splitlines():
            m = rx.search(line)
            if m:
                packs.setdefault(m.group(1), set()).add(m.group(2))
        dst_root = self.root / "dlc_text"
        for pack in sorted(packs, key=str.lower):
            archive = self.game / "update" / "x64" / "dlcpacks" / pack / "dlc.rpf"
            self.rage(["extract", "-r", "-o", dst_root / pack, archive] + sorted(packs[pack]))
        n = len(list(dst_root.rglob("global.gxt2"))) if dst_root.exists() else 0
        log("dlc: %d packs, %d global.gxt2" % (len(packs), n))

    def step_scripts(self) -> None:
        """appinternet.ysc: current (update2.rpf, else update.rpf) and 2013 (x64b.rpf)."""
        cur = None
        for rel, inner in SCRIPT_INNER.items():
            src = self.game / rel
            if not src.exists():
                continue
            out = self.root / "scripts" / "current"
            self.rage(["extract", "-r", "-o", out, src, inner])
            hits = sorted(out.rglob("appinternet.ysc"))
            if hits:
                cur = hits[0]
                log("scripts: current appinternet.ysc from %s" % rel)
                break
        if not cur:
            sys.exit("[extract] appinternet.ysc not found in update2.rpf / update.rpf")
        out = self.root / "scripts" / "x64b"
        self.rage(["extract", "-r", "-o", out, self.game / SCRIPT_2013[0], SCRIPT_2013[1]])
        if not list(out.rglob("appinternet.ysc")):
            sys.exit("[extract] appinternet.ysc not found in x64b.rpf")

    def step_textures(self) -> None:
        """Textures of the site dictionaries -> dds/<ytd>/<tex>.dds -> png/<ytd>/<tex>.png.

        sel: the .ytd of web_x64b; sel_gen: thumbnail_* and web_* of scaleform_generic (the
        update.rpf copy wins). PNG = Pillow's DDS decoder (formats it cannot read, e.g. A8,
        stay DDS only; the converter decodes those itself)."""
        from PIL import Image
        sel, sel_gen = self.root / "sel", self.root / "sel_gen"
        for d in (sel, sel_gen):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)
        for f in (self.root / "web_x64b").glob("*.ytd"):
            shutil.copy2(f, sel / f.name)
        for gen in (self.generic_dir("x64b"), self.generic_dir("update")):
            if gen and gen.is_dir():
                for pat in ("thumbnail_*.ytd", "web_*.ytd"):
                    for f in gen.glob(pat):
                        shutil.copy2(f, sel_gen / f.name)
        dds = self.root / "dds"
        if dds.exists():
            shutil.rmtree(dds)
        ytd = self.tools.ytdexport()
        for d in (sel, sel_gen):
            cmd = ytd + [str(d), str(dds)] + (["--gen9"] if self.gen9 else [])
            r = subprocess.run(cmd, capture_output=True, text=True)
            log("textures: %s: %s" % (d.name, (r.stdout.strip().splitlines() or ["?"])[-1]))
        png = self.root / "png"
        ok = bad = 0
        for f in sorted(dds.rglob("*.dds")):
            out = png / f.relative_to(dds).with_suffix(".png")
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                Image.open(f).save(out)
                ok += 1
            except Exception:
                bad += 1
        log("textures: %d PNG (%d left as DDS only)" % (ok, bad))

    # ---- paths used by the build ----------------------------------------------------
    def generic_dir(self, which: str) -> Path | None:
        base = self.root / ("gen_" + which)
        hits = sorted(base.rglob("generic")) if base.exists() else []
        hits = [h for h in hits if h.is_dir()]
        return hits[0] if hits else None

    def script(self, which: str) -> Path:
        hits = sorted((self.root / "scripts" / which).rglob("appinternet.ysc"))
        if not hits:
            sys.exit("[extract] no %s appinternet.ysc; run the extract stage" % which)
        return hits[0]

    def lang_dirs(self) -> tuple:
        """(base american_rel dir, patch american_rel dir or None)."""
        base = sorted((self.root / "lang_update2").rglob("american_rel")) if (self.root / "lang_update2").exists() else []
        patch = sorted((self.root / "lang_update").rglob("american_rel")) if (self.root / "lang_update").exists() else []
        base = [p for p in base if p.is_dir()]
        patch = [p for p in patch if p.is_dir()]
        if not base and patch:          # Legacy without update2.rpf: update.rpf holds the text
            base, patch = patch[:1], patch[1:]
        if not base:
            sys.exit("[extract] no american_rel text found; run the extract stage")
        return base[0], (patch[0] if patch else None)

    def dlc_globals(self) -> list:
        """DLC global.gxt2 in the order the game applies them: data/lang of every pack, then
        their patch/ folders (alphabetical by pack within each group)."""
        root = self.root / "dlc_text"
        files = sorted(root.rglob("global.gxt2")) if root.exists() else []
        return sorted(files, key=lambda f: ("/patch/" in f.as_posix(), str(f).lower()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Extract the GTA V files the build needs from your game install.")
    ap.add_argument("--config", help="config.toml to use (default: the one at the repository root)")
    ap.add_argument("--steps", default=",".join(STEPS), help="comma-separated steps (%s)" % ",".join(STEPS))
    ap.add_argument("--force", action="store_true", help="redo the steps even if they are marked done")
    a = ap.parse_args(argv)
    steps = [s.strip() for s in a.steps.split(",") if s.strip()]
    bad = set(steps) - set(STEPS)
    if bad:
        ap.error("unknown steps: %s" % ", ".join(sorted(bad)))
    GameFiles(load_config(a.config)).run(steps, a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
