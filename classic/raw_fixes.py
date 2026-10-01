"""Repairs for what the Internet Archive does not have.

wayback_mirror.py applies these rules to every archived HTML page, after downloading
it and before rewriting its links. The cached copy (<cache>/<GAME>/_raw) is never
modified: every build starts again from the original bytes, so the result only
depends on the lock file and on these rules.

Every rule looks for a pattern and asks the mirror what was archived (ctx.have), so
the same rule works on any page. The pages keep the original markup; what the rules
add is marked with "gta-web-local:" comments.

  video players    QuickTime / Windows Media / RealPlayer players: the Archive keeps
                   almost no video, and the mirror never downloads it. The player is
                   replaced by a box of the same size saying so.
  missing Flash    <object>/<embed> of a SWF that was never archived: same box.
  MIDI music       <embed> of a MIDI file (played by a browser plug-in that no longer
                   exists): replaced by a link to the file.
  trackers         Urchin (/__utm.js), WebSideStory (HitBox), the Google Analytics
                   loader, scripts loaded from protocol-relative URLs (AddThis,
                   Facebook) and dead web-font services: removed. (Scripts from
                   http:// hosts are removed by the link rewriter itself, and PHP
                   left in the pages as well.)
  Flash detection  period Flash detectors that run before Ruffle registers itself:
                   flashDetection.isMinimumVersion(), and the "moock fpi" pages that
                   load their detection scripts from another server and then open
                   a Flash or a no-Flash page. Those scripts are removed and the
                   page goes straight to the Flash page when its SWF was archived,
                   or to the page without Flash otherwise.
  external frames  frames that loaded another server (contest forms, stores, toolbars)
                   show a short note instead (or a blank page for toolbars).
  hit counters     counters that pick a random number image: only the archived
                   images are picked.
  twin sites       for a few sites that exist both on their own domain and under
                   rockstargames.com/<name>/ (TWIN_SITES), links to files that were
                   only archived on the other copy point to that copy.
  auto-submit      pages whose body submits a form on load, to a script that was not
                   archived or with POST (the Archive only keeps GET answers): the
                   form is replaced by a note.
"""
from __future__ import annotations

import re
import urllib.parse

MARK = "gta-web-local"

# ------------------------------------------------------------------ helpers


def comment(msg: str) -> str:
    return f"<!-- {MARK}: {msg.replace('--', '- -')} -->"


def box(label: str, w, h) -> str:
    """A black box of the size of the element it replaces."""
    width = f"{w}px" if isinstance(w, int) else (w or "320px")
    height = f"{h}px" if isinstance(h, int) else (h or "240px")
    line = height if height.endswith("px") else "240px"
    return (f'<div style="display:inline-block;width:{width};height:{height};line-height:{line};text-align:center;'
            f'background:#000;color:#bbb;font:12px Verdana,Arial,sans-serif;border:1px solid #444;'
            f'box-sizing:border-box">{label}</div>')


def notice_page(text: str) -> str:
    """A data: URL with a one-line page, for frames."""
    html = (f'<body style="background:#000;color:#bbb;font:12px Verdana,Arial,sans-serif;text-align:center;'
            f'margin-top:40px">{text}</body>')
    return "data:text/html," + urllib.parse.quote(html, safe=" :;,=/()#.-'")


def attr(tag: str, name: str):
    m = re.search(r"""(?<![\w-])""" + name + r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.I)
    if not m:
        return None
    return next(g for g in m.groups() if g is not None)


def size(tag: str, name: str):
    v = (attr(tag, name) or "").strip()
    if re.fullmatch(r"\d+", v):
        return int(v)
    if re.fullmatch(r"\d+%", v):
        return v
    return None


def outside_comments(text: str, fn) -> str:
    """Apply fn to the text between HTML comments (commented-out markup stays as it is)."""
    parts = re.split(r"(<!--.*?-->)", text, flags=re.S)
    return "".join(p if p.startswith("<!--") else fn(p) for p in parts)


# ------------------------------------------------------------------ video players and missing Flash

VIDEO_EXT = re.compile(r"\.(?:mov|qt|wmv|asf|asx|avi|mpe?g|mp4|m4v|rm|ram|rpm|flv)(?:[?#]|$)", re.I)
VIDEO_CLSID = re.compile(r"clsid:(?:02BF25D5-8C17-4B23-BC80-D3488ABDDC6B|6BF52A52-394A-11D3-B153-00C04F79FAA6|"
                         r"22D6F312-B0F6-11D0-94AB-0080C74C7E95|CFCDAA03-8BE4-11CF-B84B-0020AFBBCCFA)", re.I)
VIDEO_TYPE = re.compile(r"""\btype\s*=\s*["']?(?:video/|application/x-mplayer2|audio/x-pn-realaudio)""", re.I)
OBJECT_RX = re.compile(r"<object\b.*?</object\s*>", re.I | re.S)
EMBED_RX = re.compile(r"<embed\b[^>]*>(?:\s*</embed\s*>)?", re.I)
MEDIA_ATTR = re.compile(r"""(?<![\w-])(?:src|data|movie|filename|url)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
PARAM_RX = re.compile(r"<param\b[^>]*>", re.I)


def media_urls(markup: str) -> list[str]:
    urls = []
    for tag in re.findall(r"<(?:object|embed)\b[^>]*>", markup, re.I):
        for m in MEDIA_ATTR.finditer(tag):
            urls.append(next(g for g in m.groups() if g is not None))
    for tag in PARAM_RX.findall(markup):
        if (attr(tag, "name") or "").lower() in ("src", "movie", "filename", "url"):
            urls.append(attr(tag, "value") or "")
    return [u.strip() for u in urls if u and u.strip()]


def is_video(markup: str, urls) -> bool:
    if any(u.lower().split("?")[0].endswith(".swf") for u in urls):
        return False
    return bool(VIDEO_CLSID.search(markup) or VIDEO_TYPE.search(markup) or any(VIDEO_EXT.search(u) for u in urls))


def dims(markup: str):
    first = re.match(r"<(?:object|embed)\b[^>]*>", markup, re.I)
    w = size(first.group(0), "width") if first else None
    h = size(first.group(0), "height") if first else None
    if w is None or h is None:
        inner = re.search(r"<embed\b[^>]*>", markup, re.I)
        if inner:
            w = w if w is not None else size(inner.group(0), "width")
            h = h if h is not None else size(inner.group(0), "height")
    return (w if w is not None else 320), (h if h is not None else 240)


def players(ctx, text: str) -> str:
    def fix(markup: str):
        urls = media_urls(markup)
        if is_video(markup, urls):
            name = next((u.rsplit("/", 1)[-1] for u in urls if VIDEO_EXT.search(u)), "")
            w, h = dims(markup)
            return comment(f"video player removed, the video{' (' + name + ')' if name else ''} was not archived") + box("Video not archived", w, h)
        swfs = [u for u in urls if u.lower().split("?")[0].endswith(".swf")]
        if swfs and not any(ctx.have(u) for u in swfs):
            w, h = dims(markup)
            return comment(f"Flash movie {swfs[0].rsplit('/', 1)[-1]} was not archived") + box("Flash not archived", w, h)
        return None

    def seg(t: str) -> str:
        t = OBJECT_RX.sub(lambda m: fix(m.group(0)) or m.group(0), t)
        return EMBED_RX.sub(lambda m: fix(m.group(0)) or m.group(0), t)
    return outside_comments(text, seg)


# ------------------------------------------------------------------ MIDI background music

MIDI_EMBED_RX = re.compile(r"<embed\b[^>]*>(?:\s*</embed\s*>)?", re.I)


def midi(ctx, text: str) -> str:
    def fix(m):
        tag = m.group(0)
        src = (attr(tag, "src") or "").strip()
        if not re.search(r"\.midi?(?:[?#]|$)", src, re.I):
            return tag
        name = src.rsplit("/", 1)[-1]
        if not ctx.have(src):
            return comment(f"MIDI music {name} removed, it was not archived")
        return (comment("MIDI music played by a browser plug-in that no longer exists: linked instead") +
                f'<a href="{src}" style="font:11px Verdana,Arial,sans-serif;color:inherit">&#9835; {name} (MIDI)</a>')
    return outside_comments(text, lambda t: MIDI_EMBED_RX.sub(fix, t))


# ------------------------------------------------------------------ trackers and dead third-party services

UTM_RX = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']?[^"'\s>]*/__utm\.js["']?[^>]*>\s*</script>""", re.I)
GA_RX = re.compile(r"""\(function\s*\(\)\s*\{\s*var\s+ga\s*=\s*document\.createElement\(\s*["']script["']\s*\);"""
                   r""".*?google-analytics\.com/ga\.js.*?\}\)\(\);""", re.S)
PROTO_REL_SCRIPT_RX = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']?(//[^"'\s>]+)["']?[^>]*>\s*</script>""", re.I)
DEAD_CSS_HOSTS = ("fast.fonts.com",)
LINK_RX = re.compile(r"<link\b[^>]*>", re.I)


HITBOX_RX = re.compile(r"<!--\s*BEGIN WEBSIDESTORY CODE.*?<!--\s*END WEBSIDESTORY CODE\s*-->", re.I | re.S)


def trackers(ctx, text: str) -> str:
    text = UTM_RX.sub(lambda m: comment("Urchin counter removed (it only requested /__utm.gif)"), text)
    text = HITBOX_RX.sub(lambda m: comment("WebSideStory (HitBox) counter removed"), text)
    text = GA_RX.sub(f"/* {MARK}: Google Analytics loader removed */", text)
    text = outside_comments(text, lambda t: PROTO_REL_SCRIPT_RX.sub(
        lambda m: comment(f"external script removed: {m.group(1)}"), t))

    def link(m):
        href = attr(m.group(0), "href") or ""
        host = urllib.parse.urlsplit(href if "//" in href else "").netloc.lower()
        if host in DEAD_CSS_HOSTS:
            return comment(f"stylesheet of a web-font service that no longer exists removed: {href}")
        return m.group(0)
    return LINK_RX.sub(link, text)


# ------------------------------------------------------------------ Flash detection

FLASH_GATE_RX = re.compile(r"\bif\s*\(\s*flashDetection\.isMinimumVersion\(")
FPI_VAR = r"""\bvar\s+{0}\s*=\s*["']([^"']+)["']"""
SCRIPT_TAG_RX = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']?([^"'\s>]+)["']?[^>]*>\s*</script\s*>""", re.I)
SWF_REF_RX = re.compile(r"""["'=]\s*([^"'\s>]+\.swf)\b""", re.I)


def flash_detection(ctx, text: str) -> str:
    text = FLASH_GATE_RX.sub(f"if (true /* {MARK}: Ruffle registers its plugin after this check */ || "
                             "flashDetection.isMinimumVersion(", text)
    # "moock fpi" (Flash Player Inspector): the page sets flashPage / noFlashPage and loads
    # the detection logic from scripts on another server. With Ruffle the detection always
    # picks the Flash page, even when its SWF was never archived: decide here instead.
    fp = re.search(FPI_VAR.format("flashPage"), text)
    nfp = re.search(FPI_VAR.format("noFlashPage"), text)
    if not (fp and nfp and re.search(r"\buseRedirect\s*=\s*true", text)):
        return text
    host = urllib.parse.urlsplit(ctx.url).netloc.lower()
    ext = [m for m in SCRIPT_TAG_RX.finditer(text)
           if urllib.parse.urlsplit(urllib.parse.urljoin(ctx.url, m.group(1))).netloc.lower() != host]
    if not ext:
        return text
    flash_page, no_flash_page = fp.group(1), nfp.group(1)
    body = ctx.read(flash_page)
    swfs = SWF_REF_RX.findall(body.decode("latin-1")) if body else []
    if body and swfs and all(ctx.have(u, base=flash_page) for u in swfs):
        target, why = flash_page, "the Flash version is loaded (Ruffle)"
    elif ctx.have(no_flash_page):
        target, why = no_flash_page, f"the version without Flash is loaded (the SWF of {flash_page} was not archived)"
    else:
        return text
    for m in reversed(ext):
        text = text[:m.start()] + comment(f"Flash detection script removed: {m.group(1)}") + text[m.end():]
    # an absolute URL, so that the link rewriter points it to the local copy
    js = (f'<SCRIPT LANGUAGE="JavaScript" type="text/javascript">/* {MARK}: the Flash detection came from '
          f'another server; {why} */ window.location.replace("{urllib.parse.urljoin(ctx.url, target)}");</SCRIPT>\n')
    m = re.search(r"</head\s*>", text, re.I)
    return text[:m.start()] + js + text[m.start():] if m else js + text


# ------------------------------------------------------------------ frames that loaded other servers

# frame URL prefix -> replacement src (default: a note naming the server)
FRAME_OVERRIDES = {
    "http://toolbar.sonymusic.com/": "about:blank",  # a thin toolbar frame: leave it empty
}
# frame URL -> (frameset attributes, frames) when the site itself has a copy of what the frame showed
FRAME_LOCAL_COPIES = {
    # VC PC contest: the contest server showed left.html + main.php; rockstargames.com has left.html + main.html
    "http://63.236.94.8/contest/vcpc_replay": ('rows="*" cols="156,*" framespacing="0" frameborder="NO" border="0"',
                                              [("left.html", 'name="leftFrame" scrolling="NO" noresize'),
                                               ("main.html", 'name="mainFrame" scrolling="auto"')]),
}
FRAME_RX = re.compile(r"""<frame\b[^>]*>""", re.I)
FRAME_SRC_RX = re.compile(r"""(\bsrc\s*=\s*)(["']?)(https?://[^"'\s>]+)\2""", re.I)


def external_frames(ctx, text: str) -> str:
    for url, (fs_attrs, frames) in FRAME_LOCAL_COPIES.items():
        if url in text and all(ctx.have(f) for f, _ in frames):
            m = re.search(r"<frameset\b[^>]*>.*?</frameset\s*>", text, re.I | re.S)
            if m and url in m.group(0):
                new = (comment(f"the frame loaded {url}, which was not archived; the copies of its pages "
                               f"on this site are used") + "\n"
                       f"<frameset {fs_attrs}>\n" + "".join(f'  <frame src="{f}" {a}>\n' for f, a in frames) + "</frameset>")
                text = text[:m.start()] + new + text[m.end():]

    def frame(m):
        tag = m.group(0)
        s = FRAME_SRC_RX.search(tag)
        if not s or ctx.have(s.group(3)):
            return tag
        url = s.group(3)
        rep = next((v for k, v in FRAME_OVERRIDES.items() if url.lower().startswith(k)), None)
        if rep is None:
            host = urllib.parse.urlsplit(url).netloc
            rep = notice_page(f"Not archived: this frame loaded {host}")
        q = s.group(2) or '"'
        return comment(f"frame of another server that was not archived: {url}") + \
            tag[:s.start()] + f"{s.group(1)}{q}{rep}{q}" + tag[s.end():]
    return outside_comments(text, lambda t: FRAME_RX.sub(frame, t))


# ------------------------------------------------------------------ random hit counters

COUNTER_RX = re.compile(r"""src='([^'"]*)"\s*\+\s*(\w+)\s*\+\s*"(\.gif)'""", re.I)


def counters(ctx, text: str) -> str:
    for m in COUNTER_RX.finditer(text):
        prefix, var, ext = m.groups()
        assign = re.search(rf"\b{var}\s*=\s*rnumb\s*;", text)
        if not assign:
            continue
        have = [n for n in range(100) if ctx.have(f"{prefix}{n:02d}{ext}")]
        if not have or len(have) == 100:
            continue
        js = (f" /* {MARK}: only these counter images were archived */ var archived = {have};"
              f" if (archived.indexOf(parseInt({var}, 10)) < 0) {{ {var} = archived[Math.floor(Math.random() * archived.length)]; }}"
              f" {var} = ({var} < 10 ? '0' : '') + parseInt({var}, 10);")
        return text[:assign.end()] + js + text[assign.end():]
    return text


# ------------------------------------------------------------------ twin sites

# Sites mirrored from two places with the same files (own domain + rockstargames.com/<name>/),
# where the own domain lost files the other copy kept.
TWIN_SITES = {"sa-exsorbeo", "sa-fearitdoit"}
URL_ATTR_RX = re.compile(r"""(?P<pre>(?<=[\s<])(?:href|src|background)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)""", re.I)
MM_CALL_RX = re.compile(r"""\bMM_(?:preloadImages|swapImage)\(([^)]*)\)""")


def canon(u: str) -> str:
    """host (without www.) + path, lower case: how the mirror compares URLs."""
    p = urllib.parse.urlsplit(u if "://" in u else "http://" + u)
    host = p.netloc.lower().split(":")[0]
    return (host[4:] if host.startswith("www.") else host) + (p.path or "/").lower()


def twins(ctx, text: str) -> str:
    if ctx.site["id"] not in TWIN_SITES:
        return text
    prefixes = ctx.site["prefixes"]
    own = next((p for p in prefixes if canon(ctx.url).startswith(canon(p))), None)
    if not own:
        return text
    own_path = urllib.parse.urlsplit("http://" + own).path
    others = [p for p in prefixes if p != own]

    def twin(u: str):
        if not u or u.startswith(("#", "javascript:", "mailto:", "data:")):
            return None
        absu = urllib.parse.urljoin(ctx.url, u)
        if ctx.have(absu) or not canon(absu).startswith(canon(own)):
            return None
        p = urllib.parse.urlsplit(absu)
        rest = p.path[len(own_path):] + (f"?{p.query}" if p.query else "")
        for o in others:
            cand = "http://" + o + rest
            if ctx.have(cand):
                return cand
        return None

    def attr_sub(m):
        t = twin(m.group("url"))
        return m.group(0) if not t else f'{m.group("pre")}{m.group("q")}{t}{m.group("q")}'

    def mm_sub(m):
        return re.sub(r"""(['"])([^'"]+\.(?:gif|jpe?g|png))\1""",
                      lambda s: f"{s.group(1)}{twin(s.group(2)) or s.group(2)}{s.group(1)}", m.group(0))
    new = URL_ATTR_RX.sub(attr_sub, text)
    new = MM_CALL_RX.sub(mm_sub, new)
    if new != text:
        new += "\n" + comment(f"files not archived under {own} point to the copy of the same site under "
                              f"{', '.join(others)}") + "\n"
    return new


# ------------------------------------------------------------------ forms submitted on load

ONLOAD_SUBMIT_RX = re.compile(r"""\s+onLoad\s*=\s*["']document\.(\w+)\.submit\(\)["']""", re.I)


def autosubmit(ctx, text: str) -> str:
    m = ONLOAD_SUBMIT_RX.search(text)
    if not m:
        return text
    name = m.group(1)
    f = re.search(rf"""<form\b[^>]*\bname\s*=\s*["']?{re.escape(name)}\b[^>]*>.*?</form\s*>""", text, re.I | re.S)
    if not f:
        return text
    tag = re.match(r"<form\b[^>]*>", f.group(0), re.I).group(0)
    action = attr(tag, "action") or ""
    post = (attr(tag, "method") or "get").lower() == "post"
    if not action or (ctx.have(action) and not post):
        return text
    why = "the Archive only keeps the answers to GET requests" if post else "which was not archived"
    note = (comment(f"this page sent a form to {action} on load, {why}") + "\n" +
            box("Not archived", "100%", "100%"))
    text = text[:f.start()] + note + text[f.end():]
    return text[:m.start()] + text[m.end():]


# ------------------------------------------------------------------ entry point

RULES = (players, midi, trackers, flash_detection, external_frames, counters, twins, autosubmit)


def apply(ctx, body: bytes) -> bytes:
    """ctx: the page (ctx.url, ctx.site) and the mirror (ctx.have(url), ctx.read(url)); see wayback_mirror.Mirror."""
    text = body.decode("latin-1")
    new = text
    for rule in RULES:
        new = rule(ctx, new)
    return body if new == text else new.encode("latin-1")
