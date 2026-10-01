#!/usr/bin/env python3
"""Build the local copies of the GTA websites.

    python build.py [iv|classic|v|all] [--config config.toml]

  iv       GTA IV, TLAD and TBoGT in-game internet, from your GTA IV install (iv/build_iv.py)
  classic  GTA III, Vice City and San Andreas promo sites, from the Internet Archive (classic/build_classic.py)
  v        GTA V story-mode websites, from your GTA V install (v/build_v_sites.py)
  all      all of the above (the default); parts whose game folder is not configured are skipped

Paths come from config.toml (copy config.example.toml). Then run `python serve.py`.
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from common.config import load_config  # noqa: E402

PARTS = {
    "iv": (REPO / "iv" / "build_iv.py", "gta4"),
    "classic": (REPO / "classic" / "build_classic.py", None),
    "v": (REPO / "v" / "build_v_sites.py", "gta5"),
}


def run(part: str, config: str | None, strict: bool) -> int:
    script, needs = PARTS[part]
    if not script.exists():
        print(f"[build] {part}: {script.relative_to(REPO)} is not available, skipped")
        return 0 if not strict else 1
    if needs:
        cfg = load_config(config)
        folder = getattr(cfg, needs)
        if folder is None or not folder.exists():
            msg = f"[build] {part}: '{needs}' is not set or does not exist in {cfg.file or 'config.toml'}"
            if strict:
                print(msg)
                return 1
            print(msg + ", skipped")
            return 0
    cmd = [sys.executable, str(script)] + (["--config", config] if config else [])
    print(f"[build] {part}: {' '.join(cmd[1:])}", flush=True)
    return subprocess.run(cmd, cwd=REPO).returncode


def main():
    ap = argparse.ArgumentParser(description="Build the local copies of the GTA websites.")
    ap.add_argument("part", nargs="?", default="all", choices=["iv", "classic", "v", "all"])
    ap.add_argument("--config", help="config file (default: config.toml at the repository root)")
    a = ap.parse_args()
    config = str(Path(a.config).resolve()) if a.config else None
    if a.part == "all":
        codes = [run(p, config, strict=False) for p in PARTS]
        sys.exit(max(codes))
    sys.exit(run(a.part, config, strict=True))


if __name__ == "__main__":
    main()
