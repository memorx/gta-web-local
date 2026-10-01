#!/usr/bin/env python3
"""
Liberty Web Local
=================
Serves the GTA IV in-game internet (and its episodes) converted by iv/build_iv.py,
with a searchable index of the sites.

- Only reads the converted folder; standard library only.
- server/gta_web.py uses this module for /iv/ and the /r0/ /r1/ /r2/ page roots.

Usage:
  python server/liberty_web.py                      # <out>/iv from config.toml
  python server/liberty_web.py path/to/out/iv       # or any converted folder
  python server/liberty_web.py --port 8044 --no-browser
  python server/liberty_web.py --list               # only list what was found
"""
import argparse
import html as htmllib
import http.server
import json
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote, unquote

# ---------------------------------------------------------------------------
# Known sites (114), with our own short descriptions: (domain, note, recommended)
# ---------------------------------------------------------------------------
CATALOG = {
    "Useful": [
        ("www.eyefind.info", "The main portal and search engine of the game.", False),
        ("mail.eyefind.info", "Niko's e-mail.", False),
        ("www.goldberglignerandshyster.com", "Law firm; used in the mission Final Interview.", False),
        ("www.autoeroticar.com", "Used cars; used in the mission I'll Take Her.", False),
        ("www.love-meet.net", "Dating site: Carmen and Kiki are here.", True),
        ("www.craplist.net", "Classifieds: Alex's ad is here.", True),
        ("www.vipluxuryringtones.com", "Ringtones and phone themes.", False),
        ("www.libertycitypolice.com", "LCPD site; the padlock opens the criminal database.", True),
        ("www.whattheydonotwantyoutoknow.com", "Conspiracy forum with maps of every secret.", True),
        ("www.littlelacysurprisepageant.com", "Police sting. In the game it gives you a wanted level; here you only see the notice.", False),
    ],
    "News": [
        ("www.libertytreeonline.com", "The city's 'serious' newspaper; it follows your missions.", False),
        ("www.publiclibertyonline.com", "Left-leaning news.", False),
        ("www.weazelnews.com", "Sensationalist, conservative news.", True),
        ("www.our-own-reality.com", "Celebrity gossip.", False),
    ],
    "Blogs": [
        ("www.blogsnobs.org", "The blog platform; links to the other blogs.", False),
        ("www.bigdog.blogsnobs.org", "An art critic's blog.", False),
        ("www.darksoullock.blogsnobs.org", "Blog of a goth from Carcer City.", False),
        ("www.eddielowfilthslayer.blogsnobs.org", "Eddie Low's blog. Creepy.", True),
        ("www.fefighter2008.blogsnobs.org", "Blog of a newly divorced woman from Vice City.", False),
        ("www.inyapuper.blogsnobs.org", "Diary of a San Fierro student.", False),
        ("www.liberatedwoman.blogsnobs.org", "Alex's blog; she writes about her dates with Niko.", True),
        ("limevenus.blogsnobs.org", "Blog of a Red County teenager.", False),
        ("pychakilla.blogsnobs.org", "Poetry by a Las Venturas college student.", False),
    ],
    "Social and entertainment": [
        ("www.a-thousand-words.net", "Photo hosting.", False),
        ("www.electrictit.com", "Video site.", False),
        ("www.friendswithoutfaces.net", "Pen pals without photos.", False),
        ("www.hornyhighschoolreunions.com", "Find your old high school classmates.", False),
        ("www.lootandwank.com", "MMORPG parody.", False),
        ("www.myonlineme.com", "Virtual world with avatars.", False),
        ("www.myroomonline.net", "MySpace parody.", False),
        ("www.poker-in-the-rear.com", "Online poker.", False),
        ("www.shitster.de", "Napster parody, shut down by the police.", True),
    ],
    "Businesses and brands": [
        ("www.beanmachinecoffee.com", "Bean Machine coffee shops.", False),
        ("www.bruciesexecutivelifestyleautos.com", "The alpha lifestyle according to Brucie.", True),
        ("www.burgershot.net", "Burger Shot.", False),
        ("www.designerslave.com", "Knock-off designer clothes.", False),
        ("www.dragonbrainthemovie.com", "A fictional fantasy film.", False),
        ("www.eatbiglogs.com", "Very sugary cereal.", False),
        ("www.elchamucoroboto.com", "Robot lawn mower.", False),
        ("www.electronicwritingtablet.com", "An expensive, useless tablet.", False),
        ("www.erisfootware.com", "Eris sneakers.", False),
        ("www.eugenicsincorporated.com", "Genetically designed babies.", True),
        ("www.eunux.net", "Linux parody.", False),
        ("www.flyhighpizzapie.com", "A pizzeria that sells more than pizza.", True),
        ("www.fruitcomputers.com", "Apple parody.", True),
        ("www.gloryholethemepark.com", "Amusement park.", False),
        ("www.grype.org", "Skype parody.", False),
        ("www.huganimals.com", "Animal shelter.", False),
        ("www.krapea.com", "IKEA parody.", False),
        ("www.leftover-vacations.com", "Dubious last-minute trips.", False),
        ("www.libertycityrealestate.net", "Yusuf Amir's real estate.", False),
        ("www.lipurgex.com", "Miracle weight-loss pill.", False),
        ("www.onlineradiorevolution.com", "Domain for sale for a million.", False),
        ("www.outdatedtastes.com", "Overpriced vintage clothes.", False),
        ("www.piswasser.com", "Pißwasser beer.", False),
        ("www.redwoodcigarettes.com", "Redwood cigarettes.", False),
        ("www.rustybrownsringdonuts.com", "Rusty Brown's donuts.", False),
        ("www.sprunksoda.com", "Sprunk soda.", False),
        ("www.thebankofliberty.com", "Bank of Liberty.", False),
    ],
    "Satire and communities": [
        ("www.americantravelguide.net", "A guide for Americans travelling to Europe.", True),
        ("www.antfarmcam.net", "Ant farm webcam (down).", False),
        ("www.area53site.com", "Y2K conspiracies.", False),
        ("www.artthrob.org", "Art gallery guide.", False),
        ("www.babiesovernight.com", "'Express' babies, nothing legal.", False),
        ("www.bulimialovers.com", "Offensive satire.", False),
        ("www.chiropracticovernight.com", "Instant chiropractor degree.", False),
        ("www.domestobotlovers.com", "Fans of a household robot; shut down.", False),
        ("www.easterislandcoverup.com", "Easter Island conspiracy.", False),
        ("www.fantasyleaguebatswingers.com", "Fantasy baseball.", False),
        ("www.fistfans.com", "Adult community (not about Love Fist).", False),
        ("www.freejames.org", "Campaign to free a radio host jailed in Bali.", False),
        ("www.golfloversonline.net", "Looks like golf; really gives alibis to cheaters.", True),
        ("www.hand-jobs-online.com", "Jobs for hand models.", False),
        ("www.happyfarmersupplies.com", "'Tomatoes', wink wink.", True),
        ("www.heritagenothate.org", "Civil War re-enactments.", False),
        ("www.homecremation.com", "Home cremation kits.", True),
        ("www.homeworkfriend.org", "Homework done for you, and plagiarism.", False),
        ("www.ilovetoblow.org", "Didgeridoo community, with a double meaning.", False),
        ("www.liesdamnlies.net", "Conspiracy forum under maintenance.", False),
        ("www.loveyourmeat.com", "Anti-vegetarians.", False),
        ("www.modderstotallyrule.com", "PC case mods.", False),
        ("www.money2makemoney.com", "Pyramid scheme.", False),
        ("www.outsourceforamerica.com", "Sending American jobs abroad.", True),
        ("www.peepthatshit.com", "Tourist guide to Liberty City.", False),
        ("www.pinktorpedo.org", "'Anti-spyware' that sells your data.", False),
        ("www.pointclickshipabitch.com", "Offensive parody of mail-order brides.", False),
        ("www.roidsforlittleboys.com", "Steroids for kids (satire).", False),
        ("www.stopshavingnow.net", "A half-finished feminist site.", False),
        ("www.tobaccofacts.net", "Tobacco propaganda posing as health advice.", False),
        ("www.whymommygotfat.com", "Explaining pregnancy to kids, prudish version.", False),
        ("www.yourmexicandoctor.com", "Pharmacy without prescriptions.", True),
        ("www.yournewbabysname.com", "Very strange baby names.", False),
    ],
    "The Lost and Damned": [
        ("www.angelsofdeathonline.com", "Angels of Death club.", False),
        ("www.banditmagazine.net", "Men's magazine.", False),
        ("www.congressmanthomasstubbs.com", "Congressman Stubbs' site.", False),
        ("www.ecoelitevacations.com", "Luxury eco-tourism.", False),
        ("www.genderroledoll.com", "Toys with exaggerated stereotypes.", False),
        ("www.globeoil.net", "Globe Oil.", False),
        ("www.highmenspacetours.com", "Space tourism.", False),
        ("www.killdebtdead.com", "Debt management.", False),
        ("www.lostmc.com", "The Lost MC's site.", True),
        ("www.managingmillennials.org", "How to deal with millennials.", False),
        ("www.morningwoodspa.com", "Spa.", False),
        ("www.trainyourselftolerant.com", "Workplace sensitivity courses.", False),
        ("www.uptownriders.net", "Uptown Riders club.", False),
    ],
    "The Ballad of Gay Tony": [
        ("www.bahamamamasclub.com", "Bahama Mamas club.", False),
        ("www.bleeter.biz", "Twitter parody.", True),
        ("www.fuggie.com", "A blanket with sleeves.", False),
        ("www.goldforlife.biz", "We buy gold.", False),
        ("www.herculeslibertycity.com", "Hercules club.", False),
        ("www.maisonette9.com", "Maisonette 9 club.", False),
        ("www.princessrobotbubblegum.com", "The Princess Robot Bubblegum anime.", False),
        ("www.womenareidiots.net", "Misogynist self-help (satire).", False),
        ("www.youvebeencelebinated.com", "Gossip blog.", False),
    ],
}

OTHER = "Other"
GENERIC_LABELS = {"www", "mail"}
# Folders that are not sites: Rockstar's empty test site and resources of the conversion.
NOT_SITES = {"www.testsite.com", "_tex", "_fill", "ttf"}
HTML_EXT = {".htm", ".html"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ---------------------------------------------------------------------------
# Find the converted page roots
# ---------------------------------------------------------------------------
def has_html(folder: Path) -> bool:
    for _, _, files in os.walk(folder):
        if any(Path(f).suffix.lower() in HTML_EXT for f in files):
            return True
    return False


def find_html_roots(start: Path, max_depth: int = 5):
    """Folders named 'html' whose parent is 'pc' (GTAIV/pc/html, TBoGT/pc/html, TLAD/pc/html),
    in name order. If 'start' itself holds HTML files, it is used as is."""
    roots = []
    start_depth = len(start.parts)
    for dirpath, dirnames, _ in os.walk(start):
        dirnames.sort(key=str.lower)
        d = Path(dirpath)
        if len(d.parts) - start_depth >= max_depth:
            dirnames[:] = []
        if d.name.lower() == "html" and d.parent.name.lower() == "pc" and has_html(d):
            roots.append(d)
            dirnames[:] = []
    if not roots and has_html(start):
        roots.append(start)
    return roots


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
def scan(roots):
    files = []  # (root_idx, rel_posix)
    for i, root in enumerate(roots):
        found = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.suffix.lower() in HTML_EXT]
        files += [(i, rel) for rel in sorted(found, key=str.lower)]
    return files


def score_file(rel: str, keys: set) -> tuple:
    parts = rel.split("/")
    comp_hit = any(norm(p) in keys or norm(Path(p).stem) in keys for p in parts)
    name = parts[-1].lower()
    indexish = name.startswith(("index", "default", "main", "home"))
    return (0 if comp_hit else 1, 0 if indexish else 1, len(parts), len(rel))


def build_index(roots):
    files = scan(roots)
    claimed = set()
    sites = []
    for cat, entries in CATALOG.items():
        for domain, note, star in entries:
            labels = domain.split(".")
            if labels[0] == "www":
                labels = labels[1:]
            primary = norm(labels[0])
            if primary in GENERIC_LABELS and len(labels) > 1:
                primary = norm(labels[0] + labels[1])
            no_tld = norm(".".join(labels[:-1]))
            keys = {primary, no_tld, norm(domain), norm(".".join(labels))}
            matches = [(r, f) for r, f in files if any(k and k in norm(f) for k in keys)]
            best = None
            if matches:
                best = min(matches, key=lambda rf: score_file(rf[1], keys))
                claimed.add(best)
            sites.append({
                "domain": domain, "cat": cat, "note": note, "star": star,
                "url": f"/r{best[0]}/{quote(best[1])}" if best else None,
                "pages": len(matches),
            })
    # What the catalog does not know: grouped by folder
    others = {}
    for r, f in files:
        if (r, f) in claimed:
            continue
        key = f.split("/")[0] if "/" in f else Path(f).stem
        if key in NOT_SITES:
            continue
        others.setdefault((r, key), []).append(f)
    for (r, key), fl in sorted(others.items()):
        if any(s["url"] and f"/r{r}/{quote(key)}" in s["url"] for s in sites):
            continue  # sub-pages of a site already listed
        best = min(fl, key=lambda f: score_file(f, {norm(key)}))
        sites.append({"domain": key, "cat": OTHER, "note": f"{len(fl)} page(s)", "star": False,
                      "url": f"/r{r}/{quote(best)}", "pages": len(fl)})
    return sites, len(files)


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------
INDEX_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Liberty Web Local</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e8eaf0;--mut:#8a91a3;--acc:#f2b233;--ok:#5bd18b;--off:#555c6b}
@media (prefers-color-scheme: light){:root{--bg:#f4f5f8;--card:#fff;--line:#e2e5ec;--fg:#15171c;--mut:#5d6474;--acc:#c98200;--ok:#1f9d57;--off:#b3b8c4}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
header{padding:28px 20px 12px;max-width:1100px;margin:auto}
h1{margin:0;font-size:26px;letter-spacing:.5px}h1 span{color:var(--acc)}
.sub{color:var(--mut);margin-top:4px}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 20px;max-width:1100px;margin:auto;z-index:2;border-bottom:1px solid var(--line)}
input{width:100%;padding:11px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--fg);padding:6px 11px;border-radius:999px;cursor:pointer;font-size:13px}
.chip.on{background:var(--acc);color:#111;border-color:var(--acc)}
main{max-width:1100px;margin:auto;padding:16px 20px 60px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:1px;color:var(--mut);margin:26px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
a.card,div.card{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;transition:transform .08s,border-color .08s}
a.card:hover{transform:translateY(-2px);border-color:var(--acc)}
div.card{opacity:.45}
.dom{font-weight:600;word-break:break-all}.dom .s{color:var(--acc)}
.note{color:var(--mut);font-size:13px;margin-top:4px}
.meta{font-size:12px;margin-top:6px;color:var(--ok)}div.card .meta{color:var(--off)}
.empty{color:var(--mut);padding:30px 0;text-align:center}
</style></head><body>
<header><h1>Liberty <span>Web</span> Local</h1>
<div class="sub">__SUMMARY__</div></header>
<div class="bar"><input id="q" placeholder="Search a site or description…" autofocus>
<div class="chips" id="chips"></div></div>
<main id="list"></main>
<script>
const SITES=__DATA__;
const cats=[...new Set(SITES.map(s=>s.cat))];
let cat="All",onlyStar=false,onlyFound=true;
const chips=document.getElementById('chips');
function chip(label,active,fn){const b=document.createElement('button');b.className='chip'+(active?' on':'');b.textContent=label;b.onclick=fn;chips.appendChild(b)}
function drawChips(){chips.innerHTML='';
 ['All',...cats].forEach(c=>chip(c,cat===c,()=>{cat=c;render()}));
 chip('★ Recommended',onlyStar,()=>{onlyStar=!onlyStar;render()});
 chip('Found only',onlyFound,()=>{onlyFound=!onlyFound;render()});}
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(){drawChips();
 const q=document.getElementById('q').value.toLowerCase().trim();
 const list=document.getElementById('list');list.innerHTML='';let total=0;
 for(const c of cats){ if(cat!=='All'&&cat!==c)continue;
  const items=SITES.filter(s=>s.cat===c&&(!onlyStar||s.star)&&(!onlyFound||s.url)&&(!q||(s.domain+' '+s.note).toLowerCase().includes(q)));
  if(!items.length)continue; total+=items.length;
  const h=document.createElement('h2');h.textContent=c+' · '+items.length;list.appendChild(h);
  const g=document.createElement('div');g.className='grid';
  for(const s of items){const el=document.createElement(s.url?'a':'div');el.className='card';
   if(s.url){el.href=s.url;el.target='_blank';el.rel='noopener'}
   el.innerHTML='<div class="dom">'+(s.star?'<span class="s">★ </span>':'')+esc(s.domain)+'</div><div class="note">'+esc(s.note)+'</div><div class="meta">'+(s.url?(s.pages>1?s.pages+' pages':'1 page'):'Not found in your build')+'</div>';
   g.appendChild(el)}
  list.appendChild(g)}
 if(!total)list.innerHTML='<div class="empty">Nothing here. Try removing some filters.</div>'}
document.getElementById('q').addEventListener('input',render);render();
</script></body></html>"""


def render_index(sites, n_files, roots):
    found = sum(1 for s in sites if s["url"] and s["cat"] != OTHER)
    known = sum(len(v) for v in CATALOG.values())
    summary = (f"{found} of {known} known sites found · {n_files} HTML files · "
               f"read from: " + " | ".join(htmllib.escape(str(r)) for r in roots))
    data = json.dumps(sites, ensure_ascii=False).replace("</", "<\\/")
    return INDEX_TEMPLATE.replace("__SUMMARY__", summary).replace("__DATA__", data).encode("utf-8")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def make_handler(roots, index_bytes):
    roots = [r.resolve() for r in roots]

    def safe_join(root: Path, rel: str):
        try:
            p = (root / rel).resolve()
            p.relative_to(root)
            return p
        except (ValueError, OSError):
            return None

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if self.path.split("?")[0] in ("/", "/index.html", "/__liberty__"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(index_bytes)))
                self.end_headers()
                self.wfile.write(index_bytes)
                return
            super().do_GET()

        def translate_path(self, path):
            path = unquote(path.split("?", 1)[0].split("#", 1)[0])
            m = re.match(r"^/r(\d+)/(.*)$", path)
            if m and int(m.group(1)) < len(roots):
                # Its own root first, then the others. The episodes (TLAD/TBoGT) link sites
                # that only exist in the base game's folder, and the game falls back to the
                # base game's pc\html in the same way.
                own = roots[int(m.group(1))]
                cands, rel = [own] + [r for r in roots if r != own], m.group(2)
            else:
                cands, rel = roots, path.lstrip("/")
            for root in cands:
                p = safe_join(root, rel)
                if p and p.exists():
                    return str(p)
            return str(cands[0] / "__missing__")

        def log_message(self, *args):
            pass

    return Handler


def default_folder(config=None) -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common.config import load_config
    return load_config(config).out / "iv"


def main():
    ap = argparse.ArgumentParser(description="Browse the GTA IV in-game internet converted by iv/build_iv.py.")
    ap.add_argument("folder", nargs="?", help="converted folder (default: <out>/iv from the config)")
    ap.add_argument("--config", help="config file (default: config.toml at the repository root)")
    ap.add_argument("--port", type=int, default=8044)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--list", action="store_true", help="only list what was found and exit")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    start = Path(args.folder) if args.folder else default_folder(args.config)
    roots = find_html_roots(start) if start.exists() else []
    if not roots:
        print(f"No converted pages in {start}.\nBuild them first:  python build.py iv")
        sys.exit(1)

    sites, n_files = build_index(roots)
    found = [s for s in sites if s["url"]]
    print(f"\n{n_files} HTML files · {len(found)} browsable sites")
    for r in roots:
        print(f"  · {r}")

    if args.list:
        for s in sites:
            print(f"  {'+' if s['url'] else '-'} [{s['cat']}] {s['domain']}  {unquote(s['url'] or '')}")
        return

    handler = make_handler(roots, render_index(sites, n_files, roots))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nReady: {url}\n(Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
