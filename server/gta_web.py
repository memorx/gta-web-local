#!/usr/bin/env python3
"""
GTA Web Local
=============
One local server for the websites of the GTA saga, from GTA III to GTA V:

  /                 hub with every game
  /iii/ /vc/ /sa/   sites Rockstar published for III, Vice City and San Andreas
                    (those games have no in-game internet; copies from the Internet Archive)
  /iv/              index of the GTA IV in-game internet; pages under /r0/ /r1/ /r2/
  /v/               GTA V story-mode websites (when built)
  /_ruffle/         Ruffle, the Flash player used by the classic sites

Everything is read from the `out` folder of config.toml (built with build.py).

Usage:
  python serve.py                        (or python server/gta_web.py)
  python serve.py --port 8044 --no-browser --config my.toml
"""
import argparse
import html as htmllib
import http.server
import json
import re
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import liberty_web as lw  # noqa: E402
from common.config import load_config  # noqa: E402

GAMES = [
    ("III", "Grand Theft Auto III", "2001", "Liberty City", "iii"),
    ("VC", "Grand Theft Auto: Vice City", "2002", "Vice City", "vc"),
    ("SA", "Grand Theft Auto: San Andreas", "2004", "San Andreas", "sa"),
    ("IV", "Grand Theft Auto IV", "2008", "Liberty City", "iv"),
    ("V", "Grand Theft Auto V", "2013", "Los Santos", "v"),
]

HUB = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GTA Web Local</title>
<style>
:root{--bg:#0e1014;--card:#171a21;--line:#272c37;--fg:#e9ebf1;--mut:#8b92a4;--acc:#f2b233;--fic:#5bd18b;--off:#6f8cff;--warn:#e0784a}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f5f8;--card:#fff;--line:#e2e5ec;--fg:#15171c;--mut:#5d6474;--acc:#b87700;--fic:#1f9d57;--off:#3553d6;--warn:#c2511f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1100px;margin:auto;padding:28px 16px 70px}
h1{margin:0;font-size:28px}h1 b{color:var(--acc)}.sub{color:var(--mut);margin:6px 0 18px}
nav{display:flex;flex-wrap:wrap;gap:6px;position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:2;border-bottom:1px solid var(--line)}
nav a{border:1px solid var(--line);background:var(--card);color:var(--fg);padding:6px 12px;border-radius:999px;text-decoration:none;font-size:13px}
nav a:hover{border-color:var(--acc)}
section{margin-top:34px}
h2{margin:0 0 2px;font-size:20px}h2 small{color:var(--mut);font-weight:normal;font-size:14px}
.note{color:var(--mut);font-size:13px;margin:4px 0 12px;max-width:760px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
a.card,div.card{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
a.card:hover{border-color:var(--acc)}div.card{opacity:.5}
.t{font-weight:600}.d{color:var(--mut);font-size:12px;margin-top:3px;word-break:break-all}
.tags{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:11px;border-radius:6px;padding:1px 6px;border:1px solid currentColor}
.fic{color:var(--fic)}.off{color:var(--off)}.fl{color:var(--acc)}.w{color:var(--warn)}
.big{display:flex;align-items:center;justify-content:space-between;gap:12px}
.big .t{font-size:17px}
code{font-size:12px}
</style></head><body><div class="wrap">
<h1>GTA <b>Web</b> Local</h1>
<div class="sub">The websites of the GTA saga, from GTA III to GTA V, served from this PC.</div>
<nav>__NAV__</nav>
__SECTIONS__
</div></body></html>"""


def build_hub(classic_root: Path, iv_summary: str, v_dir: Path | None):
    sites = []
    f = classic_root / "_sites.json"
    if f.exists():
        sites = json.loads(f.read_text(encoding="utf-8"))
    nav, sections = [], []
    for key, name, year, city, slug in GAMES:
        nav.append(f'<a href="#{slug}">{htmllib.escape(name.replace("Grand Theft Auto", "GTA"))}</a>')
        body = ""
        if key in ("III", "VC", "SA"):
            gs = [s for s in sites if s["game"] == key]
            note = (f"{name} has no in-game internet. These are the sites Rockstar published at the time, "
                    f"both the ones set in the game's world and the promotional ones, copied from the Internet Archive.")
            cards = []
            for kind in ("fictional", "official"):
                for s in [x for x in gs if x["kind"] == kind]:
                    tags = f'<span class="tag {"fic" if kind == "fictional" else "off"}">{"in-universe" if kind == "fictional" else "promotional"}</span>'
                    if s.get("flash"):
                        tags += '<span class="tag fl">Flash</span>'
                    dom = s["entry"].replace("http://", "").replace("https://", "").rstrip("/")
                    if s.get("ready"):
                        cards.append(f'<a class="card" href="{s["local"]}"><div class="t">{htmllib.escape(s["title"])}</div>'
                                     f'<div class="d">{htmllib.escape(dom)}</div><div class="tags">{tags}</div></a>')
                    else:
                        cards.append(f'<div class="card"><div class="t">{htmllib.escape(s["title"])}</div>'
                                     f'<div class="d">{htmllib.escape(dom)}</div><div class="tags"><span class="tag w">not downloaded</span></div></div>')
            if not gs:
                body = '<p class="note">Not built yet. Run <code>python build.py classic</code>.</p>'
            else:
                body = f'<p class="note">{note}</p><div class="grid">{"".join(cards)}</div>'
        elif key == "IV":
            body = ('<p class="note">The internet that ships with the game, converted from your own install: GTA IV, '
                    'The Lost and Damned and The Ballad of Gay Tony.</p>'
                    f'<a class="card big" href="/iv/"><div><div class="t">Open the GTA IV index</div>'
                    f'<div class="d">{htmllib.escape(iv_summary)}</div></div><span class="tag fic">from the game</span></a>')
        else:
            if v_dir and (v_dir / "index.html").exists():
                n = 0
                try:
                    data = json.loads((v_dir / "_sites.json").read_text(encoding="utf-8"))
                    n = len(data["story"]) if isinstance(data, dict) and "story" in data else len(data)
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                body = ('<p class="note">The story-mode websites of the in-game browser, converted from your own '
                        'GTA V install with their original images, texts and fonts.</p>'
                        f'<a class="card big" href="/v/"><div><div class="t">Open the GTA V internet</div>'
                        f'<div class="d">{f"{n} sites · " if n else ""}from the game</div></div><span class="tag fic">from the game</span></a>')
            else:
                body = '<p class="note">Not built yet. Run <code>python build.py v</code> (needs your GTA V install).</p>'
        sections.append(f'<section id="{slug}"><h2>{htmllib.escape(name)} <small>{year} · {city}</small></h2>{body}</section>')
    return HUB.replace("__NAV__", "".join(nav)).replace("__SECTIONS__", "".join(sections)).encode("utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="GTA Web Local: the websites of GTA III to GTA V, served locally.")
    ap.add_argument("--config", help="config file (default: config.toml at the repository root)")
    ap.add_argument("--out", help="folder built by build.py (default: `out` from the config)")
    ap.add_argument("--port", type=int, default=8044)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    web = Path(a.out).resolve() if a.out else load_config(a.config).out
    iv_dir = web / "iv"
    classic = web / "classic"
    v_dir = web / "v"

    iv_roots = lw.find_html_roots(iv_dir) if iv_dir.exists() else []
    if iv_roots:
        sites, n_files = lw.build_index(iv_roots)
        iv_index = lw.render_index(sites, n_files, iv_roots)
        iv_index = iv_index.replace(b"<header>", b'<header><a href="/" style="color:inherit;font-size:13px">&larr; GTA Web Local</a>', 1)
        iv_summary = f"{sum(1 for s in sites if s['url'])} sites · {n_files} pages"
    else:
        iv_index = b"<p>GTA IV has not been built yet. Run <code>python build.py iv</code>.</p>"
        iv_summary = "not built yet"

    LibertyHandler = lw.make_handler(iv_roots or [web], iv_index)
    game_dirs = {"iii": classic / "III", "vc": classic / "VC", "sa": classic / "SA"}

    class Handler(LibertyHandler):
        extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{
            ".wasm": "application/wasm", ".js": "text/javascript", ".mjs": "text/javascript",
            ".swf": "application/x-shockwave-flash", ".mid": "audio/midi", ".midi": "audio/midi",
            ".mp3": "audio/mpeg", ".json": "application/json", ".xml": "text/xml",
            # period pages with server-side extensions were saved already rendered: they are HTML
            ".asp": "text/html", ".aspx": "text/html", ".php": "text/html", ".cgi": "text/html",
            ".jsp": "text/html", ".cfm": "text/html", ".shtml": "text/html"})

        def send_bytes(self, body, ctype="text/html; charset=utf-8"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"):
                return self.send_bytes(build_hub(classic, iv_summary, v_dir))
            if p in ("/iv", "/iv/", "/iv/index.html"):
                return self.send_bytes(iv_index)
            return super().do_GET()

        def translate_path(self, path):
            path = unquote(path.split("?", 1)[0].split("#", 1)[0])
            m = re.match(r"^/(iii|vc|sa)/(.*)$", path, re.I)
            if m:
                rel = m.group(2)
                order = [m.group(1).lower()] + [g for g in game_dirs if g != m.group(1).lower()]
                for g in order:  # a site can link files that ended up in another game's folder
                    base = game_dirs[g].resolve()
                    for cand in (rel, rel.rstrip("/") + "/index.html", rel + ".html"):
                        try:
                            f = (base / cand).resolve()
                            f.relative_to(base)
                        except (ValueError, OSError):
                            continue
                        if f.is_file():
                            return str(f)
                return str(game_dirs[m.group(1).lower()] / "__missing__")
            if path.startswith("/_ruffle/") or path.startswith("/v/"):
                f = (web / path.lstrip("/")).resolve()
                if str(f).startswith(str(web)):
                    return str(f)
            return super().translate_path(path)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"GTA Web Local: {url}\n  output: {web}\n  GTA IV: {iv_summary}\n(Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
