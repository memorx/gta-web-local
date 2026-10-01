"""Shared configuration for every build script.

Paths come from config.toml at the repository root (copy config.example.toml).
Any script can take --config <file> to use a different one; relative paths in
the file are resolved against the file's own folder.

    from common.config import load_config
    cfg = load_config()          # or load_config(args.config)
    cfg.gta4, cfg.gta5           # game install folders (read only, never written)
    cfg.out                      # what the server serves: out/iv, out/classic, out/v, out/_ruffle
    cfg.work                     # intermediate files: extracted game files, caches, tools
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "config.toml"


@dataclass(frozen=True)
class Config:
    file: Path | None
    gta4: Path | None
    gta5: Path | None
    out: Path
    work: Path

    def require(self, name: str) -> Path:
        """Return a game folder or stop with a clear message if it is not set."""
        value = getattr(self, name)
        if value is None or not value.exists():
            where = self.file or DEFAULT_CONFIG
            sys.exit(f"[config] '{name}' is not set or does not exist ({value}). Edit {where}.")
        return value

    @property
    def tools(self) -> Path:
        """Downloaded third-party tools (rage-cli, CodeWalker, Ruffle...)."""
        return self.work / "tools"


def _path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(os.path.expandvars(os.path.expanduser(value)))
    return (p if p.is_absolute() else base / p).resolve()


def load_config(path: str | os.PathLike | None = None) -> Config:
    file = Path(path).resolve() if path else DEFAULT_CONFIG
    data: dict = {}
    if file.exists():
        with open(file, "rb") as fh:
            data = tomllib.load(fh)
    elif path:
        sys.exit(f"[config] {file} does not exist.")
    else:
        file = None
    base = file.parent if file else REPO
    paths = data.get("paths", {})
    return Config(
        file=file,
        gta4=_path(base, paths.get("gta4")),
        gta5=_path(base, paths.get("gta5")),
        out=_path(base, paths.get("out") or "out"),
        work=_path(base, paths.get("work") or "work"),
    )


if __name__ == "__main__":
    c = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    for k in ("file", "gta4", "gta5", "out", "work", "tools"):
        print(f"{k:5} {getattr(c, k)}")
