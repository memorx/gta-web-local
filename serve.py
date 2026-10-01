#!/usr/bin/env python3
"""Start the local server for everything build.py produced.

    python serve.py [--config config.toml] [--port 8044] [--no-browser] [--out folder]

Same as `python server/gta_web.py`; see that file for the URL layout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "server"))
import gta_web  # noqa: E402

if __name__ == "__main__":
    gta_web.main()
