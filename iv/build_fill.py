#!/usr/bin/env python3
"""Build <out>/<EP>/pc/html/_fill/data.js for every converted episode.

Several blocks of the GTA IV web pages are filled by the game scripts at runtime
(dating profiles, news, e-mail, police records, ads...). whm2html leaves them as
<span class="scriptobj" data-name="...">; fill/fill.js fills them in the browser
from data.js, which this script builds from the game's own american.gxt (with the
base game as fallback, like the game does) and the textures already exported to
_tex/. The game folder is only read. data.js is game content: it is generated
locally and never part of the repository.

    python iv/build_fill.py <GTA IV folder> <out/iv>
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gxtdump  # noqa: E402
from gxt2txt import jenkins  # noqa: E402

EPISODES = {"GTAIV": "", "TLAD": "TLAD", "TBoGT": "TBoGT"}
PLAYER = {"GTAIV": "NIKO", "TLAD": "JOHNNY", "TBoGT": "LUIS"}
FILL_SRC = Path(__file__).resolve().parent / "fill"

# Rows of the base game's MAIN table used as anchors, by key hash (the key names are unknown).
H_WEATHER_ANCHOR = 0xD48E9023  # the 8 weather captions follow this row
H_STATUS_ANCHOR = 0x5805CA80   # the 3 profile status labels follow this row
H_SERVER_NOT_FOUND = 0x199B5447
H_PREV_POSTS = 0x8E0DE0FC
H_NEXT_POSTS = 0x07D033DE


def H(key):
    return jenkins(key.lower().encode())


class Text:
    """GXT tables of one episode, falling back to the base game."""

    def __init__(self, paths):
        # layers: the episode first; every key is looked up layer by layer
        self.layers = [gxtdump.tables(p) for p in paths]
        self.by_hash = {}
        for layer in self.layers:
            for rows in layer.values():
                for h, s in rows:
                    self.by_hash.setdefault(h, s)
        self.names = []
        for layer in self.layers:
            self.names += [n for n in layer if n not in self.names]

    def key(self, k, default=None):
        return clean(self.by_hash.get(H(k), default))

    def table(self, name):
        for layer in self.layers:
            if name in layer:
                return layer[name]
        return []

    def rows(self, table):
        return [s for _, s in self.table(table)]

    def all_layers(self, table):
        """[(hash, text), ...] of `table` in every layer that has it, episode first."""
        return [layer[table] for layer in self.layers if table in layer]

    def table_names(self, pattern):
        rx = re.compile(pattern)
        return [n for n in self.names if rx.fullmatch(n)]


def clean(s):
    if s is None:
        return None
    s = s.replace("~n~", "<br/>")
    s = re.sub(r"~[a-zA-Z0-9_]*~", "", s)
    return s.strip()


# ---------------------------------------------------------------- news
NAME_RX = re.compile(r"^[A-Z][\w.'\-]*( [A-Z][\w.'\-]*){0,3}$")


def is_para(s):
    return len(s) >= 150 or (len(s) >= 70 and s.rstrip()[-1:] in '.!?"' and len(s.split()) >= 12)


def parse_stories(rows):
    """[headline, subtitle, (summary), (reporter), paragraphs...] repeated."""
    stories, head, paras = [], [], []

    def flush():
        if head or paras:
            h = list(head)
            rep = h.pop() if len(h) >= 2 and NAME_RX.match(h[-1]) and len(h[-1]) < 40 else ""
            stories.append({
                "head": h[0] if h else "",
                "sub": h[1] if len(h) > 1 else "",
                "summary": " ".join(h[2:]) if len(h) > 2 else "",
                "reporter": rep,
                "paras": list(paras),
            })

    for s in rows:
        s = clean(s)
        if not s:
            continue
        if is_para(s):
            paras.append(s)
        else:
            if paras:
                flush()
                head, paras = [], []
            head.append(s)
    flush()
    return [st for st in stories if st["head"] and st["paras"]]


def news_photo_dicts(tex_root):
    """Episodes: webnews_789 -> {7,8,9}; webnews_101112 -> {10,11,12}."""
    out = {}
    for d in sorted(tex_root.glob("webnews_*")):
        digits = d.name.split("_", 1)[1]
        ids = [int(digits[i:i + 2]) for i in range(0, len(digits), 2)] if len(digits) % 2 == 0 and len(digits) > 2 else [int(c) for c in digits]
        if len(digits) == 2:
            ids = [int(digits)]
        for i in ids:
            out.setdefault(i, d.name)
    return out


def build_news(T, ep, html_root, fallback_root):
    """Liberty Tree, Weazel News and Public Liberty: base game editions + the episode's."""
    def troot(rel):
        # the texture may be in the episode's _tex or, failing that, in the base game's
        if (html_root / rel).exists():
            return rel
        if (fallback_root / rel).exists():
            return "@base/" + rel
        return None

    lt, wz, pl = [], [], []
    ep_photos = news_photo_dicts(html_root / "_tex") if ep != "GTAIV" else {}

    def num(n):
        return int(re.findall(r"\d+$", n)[0])

    def single_story(rows):
        """Weazel and Public Liberty: split stories by structure (headline + subtitle + byline)
        and glue loose fragments (a short sentence in the middle of a story) to the previous one."""
        merged = []
        for st in parse_stories(rows):
            real = st["reporter"] or st["sub"]
            if merged and not real:
                merged[-1]["paras"] += [st["head"]] + st["paras"]
            else:
                merged.append(st)
        return merged

    # base game. Liberty Tree has several stories per edition: ordered by edition.
    editions = []
    for name in sorted(T.table_names(r"LIBTR\d+"), key=num):
        n = num(name)
        ed = []
        editions.append(ed)
        for k, st in enumerate(parse_stories(T.rows(name))):
            st["id"] = f"lt{n}_{k}"
            if k == 0:
                d = f"weblctnews_{(n - 1) // 5 if n > 4 else 0}"
                # find the dictionary that holds photo n
                for cand in sorted((fallback_root / "_tex").glob("weblctnews_*")):
                    if (cand / f"storyphoto_{n}.png").exists():
                        d = cand.name
                st["photo"] = troot(f"_tex/{d}/storyphoto_{n}.png")
                st["home"] = troot(f"_tex/{d}/homephoto_{n}.png")
            ed.append(st)
    for ed in reversed(editions):  # newest edition first, stories in their order
        lt.extend(ed)
    wz_ed, pl_ed = [], []
    for name in sorted(T.table_names(r"WEAZL\d+"), key=num):
        n = num(name)
        ed = []
        for k, st in enumerate(single_story(T.rows(name))):
            st["id"] = f"wz{n}_{k}"
            if k == 0:
                for cand in sorted((fallback_root / "_tex").glob("webwzlnews_*")):
                    if (cand / f"storyphoto_{n}.png").exists():
                        st["photo"] = troot(f"_tex/{cand.name}/storyphoto_{n}.png")
            ed.append(st)
        wz_ed.append(ed)
    for name in sorted(T.table_names(r"PUBLB\d+"), key=num):
        n = num(name)
        pl_ed.append([dict(st, id=f"pl{n}_{k}") for k, st in enumerate(single_story(T.rows(name)))])

    # newest first: the front page shows the latest edition (stories in their order)
    for ed in reversed(wz_ed):
        wz.extend(ed)
    for ed in reversed(pl_ed):
        pl.extend(ed)

    # episode: LBTR1xx / WEZL1xx / PBLB1xx (TLAD) and 2xx (TBoGT)
    if ep != "GTAIV":
        epn = "1" if ep == "TLAD" else "2"
        for prefix, lst, key in (("LBTR", lt, "lt"), ("WEZL", wz, "wz"), ("PBLB", pl, "pl")):
            extra = []
            for name in sorted(T.table_names(prefix + epn + r"\d+"), key=num, reverse=True):
                n = int(num(name) % (10 ** (len(str(num(name))) - 1)))
                parser = parse_stories if key == "lt" else single_story
                for k, st in enumerate(parser(T.rows(name))):
                    st["id"] = f"{key}e{n}_{k}"
                    st["episode"] = True
                    d = ep_photos.get(n)
                    if d and k == 0:
                        if key == "lt":
                            st["photo"] = troot(f"_tex/{d}/lts.png")
                            st["home"] = troot(f"_tex/{d}/lth.png")
                        elif key == "wz":
                            st["photo"] = troot(f"_tex/{d}/wzl.png")
                    extra.append(st)
            lst[:0] = extra  # the episode's stories first, newest on top

    def dedupe(lst):
        # the game repeats some editions with the same text
        seen, out = set(), []
        for st in lst:
            k = (st["head"], st["paras"][0][:80] if st["paras"] else "")
            if k not in seen:
                seen.add(k)
                out.append(st)
        return out
    return dedupe(lt), dedupe(wz), dedupe(pl)


# ---------------------------------------------------------------- love-meet
LM_FIELDS = ["QUOTE", "JOB", "SEX", "BUILD", "LIKES", "ABOUT", "AGE", "LOC", "USER", "LIK_S", "DIS_S"]


def build_lovemeet(T):
    out = {}
    for g, table in (("f", "LOVEMTF"), ("m", "LOVEMTM")):
        rows = T.table(table)
        pos = {h: i for i, (h, _) in enumerate(rows)}
        people = []
        for i in range(12):
            p = {}
            for f in LM_FIELDS:
                h = H(f"LM_{g.upper()}_{f}_{i}")
                if h in pos:
                    p[f.lower()] = clean(rows[pos[h]][1])
            # the long "dislikes" text has no recoverable key: it always follows LIKES
            known = {pos[H(f"LM_{g.upper()}_{f}_{j}")] for f in LM_FIELDS for j in range(12) if H(f"LM_{g.upper()}_{f}_{j}") in pos}
            lh = H(f"LM_{g.upper()}_LIKES_{i}")
            if lh in pos and pos[lh] + 1 < len(rows) and pos[lh] + 1 not in known:
                p["dislikes"] = clean(rows[pos[lh] + 1][1])
            p["user"] = p.get("user") or ""
            p["dislikes"] = p.get("dislikes") or p.get("dis_s") or ""
            p["photo"] = f"_tex/webdating{'females' if g == 'f' else 'males'}/fullface_{i}.png"
            p["eyes"] = f"_tex/webdatingeyes/{'female' if g == 'f' else 'male'}eyes_{i}.png"
            people.append(p)
        out[g] = people
    return out


# ---------------------------------------------------------------- e-mail
def build_mail(T, ep):
    # base game: E_NAME_s / ES_s_e / EM_s_e / ER_s_e_k ; episodes: E1_NAME_s / E1S / E1M / E1R
    p = ("E_NAME_", "E_ADDRESS_", "ES_", "EM_", "ER_") if ep == "GTAIV" else ("E1_NAME_", "E1_ADDRESS_", "E1S_", "E1M_", "E1R_")
    senders = []
    for s in range(0, 60):
        name = T.key(f"{p[0]}{s}")
        if name is None:
            continue
        addr = T.key(f"{p[1]}{s}") or ""
        emails = []
        for e in range(0, 20):
            body = T.key(f"{p[3]}{s}_{e}")
            if body is None:
                continue
            subj = T.key(f"{p[2]}{s}_{e}") or ""
            replies = [r for r in (T.key(f"{p[4]}{s}_{e}_{k}") for k in range(3)) if r]
            if "PLACEHOLDER" in body:  # unfinished e-mails left in the text file by the developers
                continue
            emails.append({"subj": subj, "body": body, "replies": replies})
        if emails:
            senders.append({"name": name, "addr": addr, "emails": emails})
    return senders


# ---------------------------------------------------------------- LCPD
def build_lcpd(T):
    recs = {}
    ranges = list(range(0, 300)) + [b + i for b in (1000, 2000, 3000, 4000) for i in range(0, 300)]
    for n in ranges:
        sn = T.key(f"LCPDSNAME_{n}")
        if sn is None:
            continue
        recs[n] = {"s": sn, "f": T.key(f"LCPDFNAME_{n}") or "", "age": T.key(f"LCPDAGE_{n}") or "",
                   "birth": T.key(f"LCPDBIRTH_{n}") or "", "aff": T.key(f"LCPDAFF_{n}") or "",
                   "rap": T.key(f"LCPDRAP_{n}") or "", "notes": T.key(f"LCPDNOTES_{n}") or ""}
    return recs


# ---------------------------------------------------------------- blogs / celeb
# A post of the BLOGALX table ends with one of these sign-off words.
SIGNOFF = re.compile(r"(toodles|xx+|love ya|ciao|kiss kiss)\W*$", re.I)


def build_blog_alex(T):
    posts, cur = [], []
    for s in T.rows("BLOGALX") + T.rows("BLOGAL2"):
        s = clean(s)
        if not s:
            continue
        cur.append(s)
        if SIGNOFF.search(s) and len(s) < 400:
            posts.append(cur)
            cur = []
    if cur:
        posts.append(cur)
    return posts


def build_blog_eddie(T):
    posts = []
    for s in T.rows("BLOGEL"):
        s = clean(s)
        if not s:
            continue
        if posts and (len(s) < 90 or len(posts[-1][-1]) < 60):
            posts[-1].append(s)
        else:
            posts.append([s])
    return posts


def build_celeb(T):
    rows = [clean(s) for s in T.rows("CELEBIN")]
    posts, cur = [], None
    first = rows[0] if rows and len(rows[0]) > 120 else None  # the club's comment
    for s in rows[1 if first else 0:]:
        if not s:
            continue
        if len(s) < 90 and not s.endswith("."):
            cur = {"title": s, "paras": []}
            posts.append(cur)
        elif cur:
            cur["paras"].append(s)
    return {"posts": posts, "clubComment": first or ""}


# ---------------------------------------------------------------- VIP
def build_vip(T, html_root):
    names = {}
    for n in range(0, 120):
        v = T.key(f"CP_RINGTONE_{n}")
        if v:
            names[n] = v
    lists = {}
    for page in ("mp3", "sfx"):
        f = html_root / "www.vipluxuryringtones.com" / f"{page}.html"
        if f.exists():
            ids = [int(x) for x in re.findall(r"href=\"?(\d+)\.html", f.read_text(encoding="utf-8", errors="replace"))]
            lists[page] = [i for i in dict.fromkeys(ids) if i < 1000]
    r = T.rows("VIPRING")
    return {"names": names, "lists": lists, "msg": {
        "noMoney": clean(r[0]) if r else "", "ringSent": clean(r[1]) if len(r) > 1 else "",
        "themeSent": clean(r[2]) if len(r) > 2 else "", "thanks": clean(r[24]) if len(r) > 24 else ""}}


# ---------------------------------------------------------------- other
def build_search(T):
    rows = [clean(s) for s in T.rows("EYESRCH")]
    out = []
    for i in range(0, len(rows) - 2, 3):
        t, d, u = rows[i:i + 3]
        if u and ("www." in u or ".com" in u or ".net" in u or ".org" in u):
            out.append({"t": t, "d": d, "u": u})
    return out


# Order of the webadverts_N texture dictionaries (the domain list in the MAIN table).
AD_SITES_BASE = ["www.love-meet.net", "www.beanmachinecoffee.com", "www.autoeroticar.com", "www.libertytreeonline.com",
                 "www.weazelnews.com", "www.americantravelguide.net", "www.burgershot.net", "www.rustybrownsringdonuts.com",
                 "www.vipluxuryringtones.com", "www.krapea.com", "www.craplist.net", "www.publiclibertyonline.com",
                 "www.our-own-reality.com", "www.sprunksoda.com", "www.peepthatshit.com"]
AD_SITES_EP = {
    "TLAD": ["www.trainyourselftolerant.com", "www.ecoelitevacations.com", "www.genderroledoll.com", "www.globeoil.net",
             "www.banditmagazine.net", "www.killdebtdead.com", "www.morningwoodspa.com", "www.highmenspacetours.com"],
    "TBoGT": ["www.youvebeencelebinated.com", "www.fuggie.com", "www.womenareidiots.net", "www.goldforlife.biz",
              "www.bleeter.biz", "www.bahamamamasclub.com", "www.maisonette9.com", "www.princessrobotbubblegum.com",
              "www.herculeslibertycity.com"],
}
XL_SITES = ["www.love-meet.net", "www.goldberglignerandshyster.com", "www.autoeroticar.com", "www.libertytreeonline.com",
            "www.weazelnews.com"]


def build_ads(ep, html_root, base_root):
    def pick(rel):
        if (html_root / rel).exists():
            return rel
        if (base_root / rel).exists():
            return "@base/" + rel
        return None
    ads = []
    for i, site in enumerate(AD_SITES_BASE):
        ads.append({"site": site, "small": pick(f"_tex/webadverts_{i}/small.png"), "medium": pick(f"_tex/webadverts_{i}/medium.png")})
    for j, site in enumerate(AD_SITES_EP.get(ep, [])):
        i = 15 + j
        ads.append({"site": site, "small": pick(f"_tex/webadverts_{i}/small.png"), "medium": pick(f"_tex/webadverts_{i}/medium.png"), "episode": True})
    ads = [a for a in ads if a["small"] or a["medium"]]
    xl = [{"site": s, "img": pick(f"_tex/eyeadvert_0/advert_{i}.png")} for i, s in enumerate(XL_SITES)]
    if ep == "TBoGT":
        xl.insert(0, {"site": "www.youvebeencelebinated.com", "img": pick("_tex/eyeadvert_1/advert_0.png"), "episode": True})
    tv = [pick(f"_tex/webtvadverts/tvadvert_{i}.png") for i in range(10)]
    return {"ads": ads, "xl": [x for x in xl if x["img"]], "tv": [t for t in tv if t]}


def build_misc(T):
    mains = T.all_layers("MAIN")

    def row(h):
        for layer in mains:
            for hh, s in layer:
                if hh == h:
                    return clean(s)
        return None

    def after(h, n):
        for layer in mains:
            for i, (hh, _) in enumerate(layer):
                if hh == h:
                    return [clean(s) for _, s in layer[i + 1:i + 1 + n]]
        return []
    weather_text = after(H_WEATHER_ANCHOR, 8)
    g = [clean(s) for s in T.rows("GLANDS")]
    crap = [clean(s) for s in T.rows("CRAPLST")]
    alex = {}
    if len(crap) > 69:
        alex = {"title": crap[62], "loc": crap[64], "info": crap[65:69], "contact": crap[69]}
    return {
        "weather": [{"img": f"_tex/webweather/weather_{i}.png", "text": t} for i, t in enumerate(weather_text)],
        "blotter": [f"_tex/weblcpdblotter/policemap_{i}.png" for i in range(7)],
        "gland": {"noJobs": g[0] if g else "", "thanks": g[1] if len(g) > 1 else "", "submit": g[2] if len(g) > 2 else ""},
        "alexAd": alex,
        "serverNotFound": T.key("SEARCH_ERR") or row(H_SERVER_NOT_FOUND) or "",
        "prevPosts": row(H_PREV_POSTS) or "",
        "nextPosts": row(H_NEXT_POSTS) or "",
        "status": after(H_STATUS_ANCHOR, 3),
    }


def build(game: Path, out: Path, fill_src: Path = FILL_SRC, log=print):
    """Write <out>/<EP>/pc/html/_fill/{data.js,fill.js,fill.css} for every episode present in <out>."""
    base_gxt = game / "common/text/american.gxt"
    base_root = out / "GTAIV/pc/html"
    for ep, sub in EPISODES.items():
        root = out / ep / "pc/html"
        if not root.exists():
            continue
        gxt = game / sub / "common/text/american.gxt" if sub else base_gxt
        T = Text([gxt] + ([base_gxt] if sub else []))
        lt, wz, pl = build_news(T, ep, root, base_root)
        data = {
            "ep": ep, "player": PLAYER[ep],
            "lovemeet": build_lovemeet(T),
            "mail": build_mail(T, ep),
            "lcpd": build_lcpd(T),
            "blogs": {"alex": build_blog_alex(T), "eddie": build_blog_eddie(T)},
            "celeb": build_celeb(T),
            "vip": build_vip(T, base_root),
            "search": build_search(T),
            "news": {"libtree": lt, "weazel": wz, "publib": pl},
            "misc": build_misc(T),
        }
        data.update(build_ads(ep, root, base_root))
        dst = root / "_fill"
        dst.mkdir(parents=True, exist_ok=True)
        js = "window.LIBERTY=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
        (dst / "data.js").write_text(js, encoding="utf-8")
        for f in ("fill.js", "fill.css"):
            shutil.copyfile(fill_src / f, dst / f)
        log(f"  {ep}: profiles {len(data['lovemeet']['f'])}+{len(data['lovemeet']['m'])}, senders {len(data['mail'])} "
            f"({sum(len(s['emails']) for s in data['mail'])} e-mails), LCPD records {len(data['lcpd'])}, "
            f"news LT {len(lt)} WZ {len(wz)} PL {len(pl)}, search {len(data['search'])}, ads {len(data['ads'])}, "
            f"posts Alex {len(data['blogs']['alex'])} Eddie {len(data['blogs']['eddie'])}, celeb {len(data['celeb']['posts'])}, "
            f"{len(js) // 1024} KB")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        sys.exit(__doc__)
    build(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    main()
