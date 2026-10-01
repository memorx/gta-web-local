"""Third-party tools for the GTA V build, downloaded into <work>/tools at pinned versions.

Nothing here is vendored in the repository. Each tool is fetched once from its official
release page, checked against a SHA-256 digest and unpacked under cfg.tools:

  rage-cli     VIRUXE/rage-cli v0.22.0 (Unlicense)         RPF extraction; reads the
               archive keys from your own GTA5.exe / GTA5_Enhanced.exe
  JPEXS FFDec  jindrapetrik/jpexs-decompiler 26.3.0 (GPL-3) ActionScript export of the site
               movies and compilation of the host shim (needs Java 8+)
  CodeWalker   dexyfex/CodeWalker @ 485d56be (source "released for educational purposes
               only", no licence file); only CodeWalker.Core is compiled, to read the
               textures of .ytd files (gen9 textures of the Enhanced edition included)
  .NET SDK     8.0.425 through Microsoft's dotnet-install script (only if no .NET 8+ SDK is
               on PATH). The build restores SharpDX 4.2.0 (MIT) from NuGet for CodeWalker.Core
  Ruffle       the pinned web build of classic/build_classic.py (MIT/Apache-2.0), copied to
               <out>/_ruffle/ when a GTA V-only build has none

ytdexport (v/ytdexport, our own few lines of C#) is compiled against that CodeWalker.Core.

    python v/thirdparty.py            download / build everything that is missing
    python v/thirdparty.py --check    only report what is there
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.config import load_config  # noqa: E402

IS_WIN = os.name == "nt"

RAGE_VERSION = "0.22.0"
RAGE_ASSETS = {  # asset name -> sha256 (release SHA256SUMS)
    "windows": ("rage-windows-x86_64.exe", "e0c9ec71fa09e046ccb47304fe95ac2a5485d05ba06031303e36b5d6ea0b314d"),
    "linux": ("rage-linux-x86_64", "54af177ecbae2b2a17ff36e920803378b191a160752b4a372bf080f03375f011"),
}
RAGE_URL = "https://github.com/VIRUXE/rage-cli/releases/download/v%s/%s"

FFDEC_VERSION = "26.3.0"
FFDEC_URL = "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version%s/ffdec_%s.zip"
FFDEC_SHA256 = "35f4930eb7c380afe66f2117f90b006deac0631473ad7500bb39c78f68645ecd"

CODEWALKER_COMMIT = "485d56bec00262ed7fa472261cce7bbc6202b96e"
CODEWALKER_URL = "https://codeload.github.com/dexyfex/CodeWalker/zip/%s"
CODEWALKER_SHA256 = "829aff6966d78abe95fdf473d7085d4592af578529f0c97135a1c3d91bb49369"

DOTNET_VERSION = "8.0.425"   # any .NET 8+ SDK already on PATH is used instead
DOTNET_INSTALL = {True: "https://dot.net/v1/dotnet-install.ps1", False: "https://dot.net/v1/dotnet-install.sh"}


def log(msg: str) -> None:
    print("[tools] " + msg, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dst: Path, digest: str | None = None) -> Path:
    """Download url to dst (atomically) and check its SHA-256 if given."""
    if dst.exists() and (digest is None or sha256(dst) == digest):
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    log("downloading %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "gta-web-local-build"})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh, 1 << 20)
    if digest:
        got = sha256(tmp)
        if got != digest:
            tmp.unlink()
            sys.exit("[tools] checksum mismatch for %s\n  expected %s\n  got      %s" % (url, digest, got))
    os.replace(tmp, dst)
    return dst


class Tools:
    """Paths of the tools under cfg.tools; each getter fetches what is missing."""

    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        self.root = Path(self.cfg.tools)
        self.dl = self.root / "downloads"

    # ---- rage-cli -----------------------------------------------------------------
    def rage(self) -> Path:
        key = "windows" if IS_WIN else "linux"
        if platform.machine().lower() not in ("amd64", "x86_64"):
            sys.exit("[tools] rage-cli is only published for x86-64 Windows and Linux")
        name, digest = RAGE_ASSETS[key]
        exe = self.root / ("rage-" + RAGE_VERSION) / name
        if not exe.exists() or sha256(exe) != digest:
            download(RAGE_URL % (RAGE_VERSION, name), exe, digest)
            if not IS_WIN:
                exe.chmod(0o755)
        return exe

    def rage_env(self, game_exe: Path) -> dict:
        """Environment for rage-cli: keys read from your own game executable, cached in tools."""
        env = dict(os.environ)
        env["GTAV_PATH"] = str(game_exe)
        env["RAGE_NO_UPDATE_CHECK"] = "1"
        env["RAGE_KEYS_CACHE"] = str(self.root / "rage-keys")
        return env

    # ---- JPEXS FFDec + Java ------------------------------------------------------
    def java(self) -> str:
        home = os.environ.get("JAVA_HOME")
        cands = []
        if home:
            cands.append(str(Path(home) / "bin" / ("java.exe" if IS_WIN else "java")))
        which = shutil.which("java")
        if which:
            cands.append(which)
        for c in cands:
            try:
                r = subprocess.run([c, "-version"], capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    return c
            except OSError:
                pass
        sys.exit("[tools] Java 8 or newer is needed by JPEXS FFDec (ActionScript export and the host "
                 "shim). Install a JRE/JDK (e.g. Eclipse Temurin 21) and put 'java' on PATH or set JAVA_HOME.")

    def ffdec(self) -> Path:
        jar = self.root / ("ffdec-" + FFDEC_VERSION) / "ffdec-cli.jar"
        if not jar.exists():
            z = download(FFDEC_URL % (FFDEC_VERSION, FFDEC_VERSION), self.dl / ("ffdec_%s.zip" % FFDEC_VERSION),
                         FFDEC_SHA256)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(jar.parent)
        if not jar.exists():
            sys.exit("[tools] ffdec-cli.jar not found after unpacking JPEXS %s" % FFDEC_VERSION)
        return jar

    def ffdec_cmd(self) -> list:
        return [self.java(), "-Djava.awt.headless=true", "-jar", str(self.ffdec())]

    # ---- .NET SDK, CodeWalker, ytdexport -------------------------------------------
    def _sdk_ok(self, dotnet: str) -> bool:
        try:
            r = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, timeout=120)
        except OSError:
            return False
        for line in r.stdout.splitlines():
            try:
                if int(line.split(".")[0]) >= 8:
                    return True
            except ValueError:
                pass
        return False

    def dotnet(self) -> str:
        local = self.root / "dotnet" / ("dotnet.exe" if IS_WIN else "dotnet")
        if local.exists() and self._sdk_ok(str(local)):
            return str(local)
        system = shutil.which("dotnet")
        if system and self._sdk_ok(system):
            return system
        log("no .NET 8+ SDK found; installing the .NET SDK %s into %s" % (DOTNET_VERSION, local.parent))
        script = download(DOTNET_INSTALL[IS_WIN], self.dl / ("dotnet-install.ps1" if IS_WIN else "dotnet-install.sh"))
        if IS_WIN:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                   "-Version", DOTNET_VERSION, "-InstallDir", str(local.parent), "-NoPath"]
        else:
            cmd = ["bash", str(script), "--version", DOTNET_VERSION, "--install-dir", str(local.parent), "--no-path"]
        subprocess.run(cmd, check=True)
        if not self._sdk_ok(str(local)):
            sys.exit("[tools] the .NET SDK install did not work; install the .NET 8 SDK and put 'dotnet' on PATH")
        return str(local)

    def codewalker(self) -> Path:
        src = self.root / ("CodeWalker-" + CODEWALKER_COMMIT)
        if not (src / "CodeWalker.Core" / "CodeWalker.Core.csproj").exists():
            z = download(CODEWALKER_URL % CODEWALKER_COMMIT, self.dl / ("CodeWalker-%s.zip" % CODEWALKER_COMMIT[:12]),
                         CODEWALKER_SHA256)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(self.root)
        return src

    def ytdexport(self) -> list:
        """Command prefix to run ytdexport (built on first use)."""
        out = self.root / "ytdexport" / "bin"
        dll = out / "ytdexport.dll"
        dotnet = self.dotnet()
        src_files = [HERE / "ytdexport" / "Program.cs", HERE / "ytdexport" / "ytdexport.csproj"]
        stamp = out / "built-from.txt"
        want = "%s %s\n" % (CODEWALKER_COMMIT, "".join(sha256(p)[:12] for p in src_files))
        if not dll.exists() or not stamp.exists() or stamp.read_text() != want:
            cw = self.codewalker()
            proj = self.root / "ytdexport" / "src"
            proj.mkdir(parents=True, exist_ok=True)
            for p in src_files:
                shutil.copy2(p, proj / p.name)
            log("building ytdexport against CodeWalker.Core %s" % CODEWALKER_COMMIT[:12])
            r = subprocess.run([dotnet, "build", str(proj / "ytdexport.csproj"), "-c", "Release", "-o", str(out),
                                "-p:CodeWalkerDir=%s" % cw, "-nologo", "-v", "q"],
                               capture_output=True, text=True)
            if r.returncode != 0 or not dll.exists():
                sys.exit("[tools] ytdexport build failed:\n%s" % (r.stdout + r.stderr)[-3000:])
            stamp.write_text(want)
        return [dotnet, str(dll)]

    # ---- Ruffle (shared with the classic sites) ---------------------------------------
    def ruffle(self) -> Path:
        """Folder with the pinned Ruffle web build (version and checksum: classic/build_classic.py)."""
        import importlib.util
        src = HERE.parent / "classic" / "build_classic.py"
        spec = importlib.util.spec_from_file_location("build_classic", src)
        if spec is None or not src.exists():
            sys.exit("[tools] %s is missing; it pins the Ruffle version the pages use" % src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return Path(mod.get_ruffle(self.root))

    def install_ruffle(self, out: Path) -> bool:
        """Copy Ruffle to <out>/_ruffle/ unless it is already there. True if copied."""
        dst = Path(out) / "_ruffle"
        if (dst / "ruffle.js").exists():
            return False
        src = self.ruffle()
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file():
                shutil.copyfile(f, dst / f.name)
        log("Ruffle -> %s" % dst)
        return True

    def all(self) -> None:
        log("rage-cli     %s" % self.rage())
        log("JPEXS FFDec  %s (java: %s)" % (self.ffdec(), self.java()))
        log("ytdexport    %s" % " ".join(self.ytdexport()))

    def report(self) -> None:
        for name, p in (("rage-cli", self.root / ("rage-" + RAGE_VERSION)),
                        ("JPEXS", self.root / ("ffdec-" + FFDEC_VERSION)),
                        ("CodeWalker", self.root / ("CodeWalker-" + CODEWALKER_COMMIT)),
                        ("ytdexport", self.root / "ytdexport" / "bin" / "ytdexport.dll"),
                        (".NET SDK (local)", self.root / "dotnet")):
            log("%-17s %s %s" % (name, "ok     " if p.exists() else "missing", p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download and build the third-party tools of the GTA V build.")
    ap.add_argument("--config", help="config.toml to use (default: the one at the repository root)")
    ap.add_argument("--check", action="store_true", help="only report what is already there")
    a = ap.parse_args(argv)
    t = Tools(load_config(a.config))
    if a.check:
        t.report()
    else:
        t.all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
