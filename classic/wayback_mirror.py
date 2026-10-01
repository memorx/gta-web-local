#!/usr/bin/env python3
"""Local mirror of sites archived in the Wayback Machine (GTA III, Vice City, San Andreas).

For each site: take the list of archived URLs (from the lock file, or from the CDX API
within the site's time window), download each one as its original bytes (`id_`
captures), apply the repair rules of raw_fixes.py and rewrite the links so the pages
work locally. Every page loads Ruffle for Flash.

    python classic/wayback_mirror.py sites.json <out> [--cache DIR] [--lock DIR]
                                     [--only ID[,ID]] [--delay 0.8] [--workers 1] [--rewrite-only]
                                     [--refresh] [--assets-pass] [--externals] [--write-lock DIR]

  <out>          served copy: <out>/<GAME>/<host>/<path>
  --cache DIR    downloads and lists: DIR/<GAME>/_raw/<host>/<path> (original bytes, never
                 modified) and DIR/<GAME>/_manifest/<id>.json (default: <out>)
  --lock DIR     DIR/<id>.json pins the rows of each site (URL, capture time, SHA-1 of the
                 bytes) so every build downloads exactly the same captures. Sites without a
                 lock file are listed from the CDX API.
  --refresh      list the locked sites from the CDX API again (keeping the rows added by
                 hand in the lock and dropping the ones it marks as pruned)
  --assets-pass  second CDX listing per site WITHOUT an end date, only non-HTML resources
                 (images, SWF, audio, XML): many files of the time were only captured later
  --externals    also copy the scripts/CSS/images/SWF the pages load from other hosts
  --write-lock   write the lock files for the processed sites from the current manifests

sites.json: list of {game, id, title, kind, prefixes:[...], ts, from, to, entry}
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raw_fixes  # noqa: E402

UA = "Mozilla/5.0 (gta-web-local: offline mirror of GTA promo sites)"
SKIP_EXT = {".mov", ".avi", ".mpg", ".mpeg", ".wmv", ".zip", ".sit", ".exe", ".rar", ".dmg", ".hqx", ".bin", ".iso",
            ".rm", ".ram", ".asf", ".mp4", ".m4v", ".flv", ".pdf"}
BIN_EXT = {".gif", ".jpg", ".jpeg", ".png", ".bmp", ".ico", ".swf", ".mp3", ".wav", ".mid", ".midi", ".js", ".css", ".xml", ".dcr"}
MAGIC = {".gif": (b"GIF8",), ".jpg": (b"\xff\xd8",), ".jpeg": (b"\xff\xd8",), ".png": (b"\x89PNG",),
         ".swf": (b"FWS", b"CWS", b"ZWS")}
MAX_BYTES = 12 * 1024 * 1024
HTML_EXT = (".html", ".htm", ".shtml", ".php", ".asp", ".aspx", ".cfm", ".jsp", ".cgi")
TEXT_EXT = (".css", ".js", ".xml", ".txt")
ROW_KEYS = ("ts", "url", "mime", "len", "ext", "cap", "sha1")

# ------------------------------------------------------------------ network


class Net:
    """HTTP client for the Archive: one persistent (keep-alive) connection per host.

    The Internet Archive limits how many NEW connections a client opens: a fresh
    connection per request gets refused after a few dozen files, while one kept-alive
    connection serves thousands of requests. Redirects are followed by hand on the
    same connection. One Net per thread."""

    RETRY = (429, 500, 502, 503, 504, 520, 522, 524)

    def __init__(self, delay):
        self.delay, self.last = delay, 0.0
        self.conns = {}

    def _conn(self, scheme, host):
        key = (scheme, host)
        c = self.conns.get(key)
        if c is None:
            cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
            c = self.conns[key] = cls(host, timeout=60)
        return c

    def _drop(self, scheme, host):
        c = self.conns.pop((scheme, host), None)
        if c is not None:
            c.close()

    def _once(self, url):
        """One request on the kept-alive connection: (status, headers, body)."""
        gap = time.time() - self.last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        p = urllib.parse.urlsplit(url)
        scheme, host = p.scheme.lower(), p.netloc
        if host.lower() == "web.archive.org":
            scheme = "https"
        path = urllib.parse.quote(p.path or "/", safe="/%:@!$&'()*+,;=~-._") + (f"?{p.query}" if p.query else "")
        for fresh in (False, True):
            c = self._conn(scheme, host)
            self.last = time.time()
            try:
                c.request("GET", path, headers={"User-Agent": UA})
                r = c.getresponse()
                body = r.read(MAX_BYTES + 1)
                if not r.isclosed():  # over the size limit: the rest is not wanted
                    self._drop(scheme, host)
                elif (r.getheader("Connection") or "").lower() == "close":
                    self._drop(scheme, host)
                return r.status, r, body
            except (http.client.RemoteDisconnected, http.client.CannotSendRequest, http.client.ResponseNotReady,
                    ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                self._drop(scheme, host)
                if fresh:
                    raise
                # the server closed the idle connection: reconnect once
            except Exception:
                self._drop(scheme, host)
                raise

    def get(self, url, tries=6):
        """(status, final url, content type, body). 404/403/410 are final; other errors are retried.
        When the Archive refuses connections (its rate limit), wait a minute and try again."""
        wait = 5
        refused = 0
        attempt = 0
        while attempt < tries:
            attempt += 1
            try:
                cur = url
                for _ in range(10):
                    st, r, body = self._once(cur)
                    loc = r.getheader("Location")
                    if st in (301, 302, 303, 307, 308) and loc:
                        cur = urllib.parse.urljoin(cur, loc)
                        continue
                    break
                if st == 200:
                    return st, cur, r.getheader("Content-Type", ""), body
                if st in self.RETRY:
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                return st, cur, "", b""
            except Exception as e:
                if isinstance(e, ConnectionRefusedError) and refused < 20:
                    refused += 1
                    attempt -= 1  # throttled, not failed
                    if refused == 1:
                        print("  the Archive is refusing connections (rate limit); waiting...", flush=True)
                    time.sleep(60)
                    continue
                time.sleep(wait)
                wait = min(wait * 2, 120)
        return 0, url, "", b""


# ------------------------------------------------------------------ paths


def canon_host(host):
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def ext_of(url):
    return os.path.splitext(urllib.parse.urlsplit(url).path.lower())[1]


def local_rel(url, mime=""):
    """Original URL -> local path relative to the game folder (host/path)."""
    p = urllib.parse.urlsplit(url)
    host = canon_host(p.netloc)
    path = urllib.parse.unquote(p.path or "/")
    path = re.sub(r"/{2,}", "/", path)
    if path.endswith("/"):
        path += "index.html"
    else:
        last = path.rsplit("/", 1)[-1]
        if "." not in last:
            path += "/index.html" if (not mime or "html" in mime) else ""
    if p.query:
        q = re.sub(r"[^A-Za-z0-9=_\-.]", "_", p.query)[:80]
        stem, dot, ext = path.rpartition(".")
        path = f"{stem}__{q}.{ext}" if dot and "/" not in ext else f"{path}__{q}"
    path = "/".join(re.sub(r'[<>:"|?*\\]', "_", seg) for seg in path.split("/"))
    return f"{host}{path}"


def rel_link(from_rel, to_rel):
    a = from_rel.split("/")[:-1]
    b = to_rel.split("/")
    i = 0
    while i < len(a) and i < len(b) - 1 and a[i].lower() == b[i].lower():  # NTFS is case-insensitive
        i += 1
    out = "../" * (len(a) - i) + "/".join(b[i:])
    return urllib.parse.quote(out, safe="/#?=&%._-~+,;:@!$'()*")


def prefix_path(prefix):
    p = urllib.parse.urlsplit(prefix if "://" in prefix else "http://" + prefix)
    return canon_host(p.netloc) + (p.path or "/").lower()


def under_prefix(url, prefix):
    """Is the URL really under the prefix? (the CDX SURT prefix search also returns
    'grandtheftauto3/' when asked for 'grandtheftauto/')."""
    p = urllib.parse.urlsplit(url)
    key = canon_host(p.netloc) + (p.path or "/").lower()
    pp = prefix_path(prefix)
    return key.startswith(pp) or key + "/" == pp


# ------------------------------------------------------------------ CDX


class CDXError(RuntimeError):
    pass


def cdx_list(net, prefix, frm, to, non_html_only=False):
    p = urllib.parse.urlsplit(prefix if "://" in prefix else "http://" + prefix)
    h = canon_host(p.netloc)
    rows = {}
    for host in sorted({p.netloc.lower(), h, "www." + h}):
        q = host + (p.path or "/")
        resume = None
        while True:
            params = [("url", q), ("matchType", "prefix"), ("output", "json"), ("filter", "statuscode:200"),
                      ("fl", "urlkey,timestamp,original,mimetype,length"), ("collapse", "urlkey"),
                      ("limit", "5000"), ("showResumeKey", "true")]
            if frm:
                params.append(("from", frm))
            if to:
                params.append(("to", to))
            if non_html_only:
                params.append(("filter", "!mimetype:text/html"))
            if resume:
                params.append(("resumeKey", resume))
            st, _, _, body = net.get("http://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(params))
            if st != 200:
                # a silent partial list would change the mirror: stop instead
                raise CDXError(f"CDX query failed (HTTP {st}) for {q}; try again later")
            try:
                data = json.loads(body.decode("utf-8", "replace") or "[]")
            except ValueError:
                raise CDXError(f"CDX returned invalid JSON for {q}; try again later")
            resume = None
            if data and data[-1] and len(data[-1]) == 1:
                resume = data[-1][0]
                data = data[:-2] if len(data) >= 2 and data[-2] == [] else data[:-1]
            for r in data[1:]:
                if len(r) < 5:
                    continue
                key, ts, orig, mime, length = r
                if not under_prefix(orig, prefix):
                    continue
                rows.setdefault(key, {"ts": ts, "url": orig, "mime": mime, "len": int(length) if length.isdigit() else 0})
            if not resume:
                break
    return rows


def wanted(row):
    u = row["url"].lower().split("?")[0]
    ext = os.path.splitext(u)[1]
    m = row["mime"].lower()
    if ext in SKIP_EXT or m.startswith("video/"):
        return False
    if ext in BIN_EXT and m.startswith("text/html"):
        return False  # error page saved under an image URL
    if m in ("application/zip", "application/x-stuffit"):
        return False
    if row["len"] and row["len"] > MAX_BYTES:
        return False
    if "robots.txt" in u:
        return False
    return True


IMAGE_MAGIC = MAGIC[".gif"] + MAGIC[".jpg"] + MAGIC[".png"]


def body_ok(url, body):
    ext = ext_of(url)
    if ext in (".gif", ".jpg", ".jpeg", ".png"):
        # any image will do: some servers sent JPEG bytes under a .png name, and browsers sniff
        return body.startswith(IMAGE_MAGIC)
    if ext in MAGIC:
        return body.startswith(MAGIC[ext])
    if ext in BIN_EXT and ext not in (".js", ".css", ".xml"):
        head = body.lstrip()[:20].lower()
        return not head.startswith((b"<!doctype", b"<html", b"<head"))
    return True


def same_resource(final_url, orig):
    """id_ follows archived redirects: an image can end up on another page."""
    m = re.search(r"/web/\d+(?:[a-z]{2}_)?/(.+)$", final_url)
    if not m:
        return True
    a, b = urllib.parse.urlsplit(m.group(1)), urllib.parse.urlsplit(orig)
    return canon_host(a.netloc) == canon_host(b.netloc) and (a.path or "/").lower().rstrip("/") == (b.path or "/").lower().rstrip("/")


def capture_of(final_url):
    m = re.search(r"/web/(\d{14})", final_url)
    return m.group(1) if m else ""


# ------------------------------------------------------------------ rewriting

ATTR_RX = re.compile(r'''(?P<pre>(?<=[\s<])(?:href|src|background|action|data|codebase|lowsrc|value|movie)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)''', re.I)
CSS_URL_RX = re.compile(r'''url\(\s*(["']?)([^"')]+)\1\s*\)''', re.I)
ABS_RX = re.compile(r'''https?://[A-Za-z0-9.\-]+(?::\d+)?/[^\s"'<>()\\]*|https?://[A-Za-z0-9.\-]+(?=["'\s<>)/])''')
WAYBACK_RX = re.compile(r'''https?://web\.archive\.org/web/\d+(?:[a-z]{2}_)?/''', re.I)
SCRIPT_RX = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.I | re.S)
JS_ROOTREL_RX = re.compile(r'''(["'])(/[A-Za-z0-9_][^"'\s<>]*)''')
PHP_RX = re.compile(r"<\?\s*\$Analytics->\w+\(\)\s*;?\s*\?>")

# Period Flash detectors look for navigator.plugins['Shockwave Flash'] before Ruffle registers
# its own plugin: this shim makes them take the Flash branch.
FLASH_SHIM = ("<script>(function(){try{if(navigator.plugins&&navigator.plugins['Shockwave Flash'])return;"
              "var p={name:'Shockwave Flash',filename:'Flash.ocx',description:'Shockwave Flash 32.0 r0',version:'32.0.0.0',length:1};"
              "var m={type:'application/x-shockwave-flash',suffixes:'swf',description:'Shockwave Flash',enabledPlugin:p};p[0]=m;"
              "var P=navigator.plugins,M=navigator.mimeTypes;"
              "Object.defineProperty(navigator,'plugins',{configurable:true,value:new Proxy(P,{get:function(t,k){if(k==='Shockwave Flash'||k===String(t.length))return p;"
              "if(k==='length')return t.length+1;var v=t[k];return typeof v==='function'?v.bind(t):v;}})});"
              "Object.defineProperty(navigator,'mimeTypes',{configurable:true,value:new Proxy(M,{get:function(t,k){if(k==='application/x-shockwave-flash')return m;"
              "var v=t[k];return typeof v==='function'?v.bind(t):v;}})});}catch(e){}})();</script>")


EXT_SCRIPT_RX = re.compile(r'''<script\b[^>]*\bsrc\s*=\s*["']?(https?://[^"'\s>]+)["']?[^>]*>\s*</script>''', re.I)
EXT_IMG_RX = re.compile(r'''(?P<pre>(?<=[\s<])(?:src|background)\s*=\s*)(?P<q>["']?)(?P<url>https?://[^"'\s>]+)(?P=q)''', re.I)
IMG_EXT = (".gif", ".jpg", ".jpeg", ".png", ".bmp")


class Rewriter:
    def __init__(self, url_map, qless_map, dir_game, game, prefixes, ts=""):
        self.url_map, self.qless, self.dir_game = url_map, qless_map, dir_game
        self.game = game
        self.prefixes = [prefix_path(p) for p in prefixes]
        self.ts = ts

    @staticmethod
    def norm(url):
        p = urllib.parse.urlsplit(url)
        path = re.sub(r"/{2,}", "/", p.path or "/")
        return f"{canon_host(p.netloc)}{path.lower()}" + (f"?{p.query}" if p.query else "")

    def lookup(self, absu):
        key = self.norm(absu)
        hit = self.url_map.get(key)
        if hit is None and not key.split("?")[0].endswith("/"):
            hit = self.url_map.get(key.split("?")[0] + "/" + ("?" + key.split("?")[1] if "?" in key else ""))
        if hit is None and "?" in key:
            hit = self.qless.get(key.split("?")[0])  # session parameters: any archived variant
        if hit is None:
            # sites with two prefixes (own domain + rockstargames.com/<site>/): same files
            base = key.split("?")[0]
            for pa in self.prefixes:
                if base.startswith(pa):
                    for pb in self.prefixes:
                        if pb != pa:
                            hit = self.url_map.get(pb + base[len(pa):])
                            if hit:
                                break
                if hit:
                    break
        return hit

    def target(self, base_url, raw, page_rel):
        raw = raw.strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:", "data:", "about:")):
            return None
        raw = WAYBACK_RX.sub("", raw)
        absu = urllib.parse.urljoin(base_url, raw)
        if not absu.startswith("http"):
            return None
        frag = ""
        if "#" in absu:
            absu, frag = absu.split("#", 1)
            frag = "#" + frag
        hit = self.lookup(absu)
        if hit is None:
            return None
        game, rel = hit
        if game == self.game:
            return rel_link(page_rel, rel) + frag
        up = "../" * (page_rel.count("/") + 1)
        return up + urllib.parse.quote(f"{game.lower()}/{rel}", safe="/#?=&%._-~+,;:@!$'()*") + frag

    def fix_rootrel_js(self, js, base_url):
        """'/advertisingcouncil/what/x' in JS -> '/iii/rockstargames.com/advertisingcouncil/what/x'."""
        host = canon_host(urllib.parse.urlsplit(base_url).netloc)

        def sub(m):
            path = m.group(2)
            first = host + "/" + path.lstrip("/").split("/")[0].lower() + "/"
            game = self.dir_game.get(first)
            if not game or "/" not in path[1:]:
                return m.group(0)
            return f"{m.group(1)}/{game.lower()}/{host}{path}"
        return JS_ROOTREL_RX.sub(sub, js)

    def rewrite_html(self, text, base_url, page_rel, root):
        text = PHP_RX.sub("", text)

        def attr(m):
            t = self.target(base_url, m.group("url"), page_rel)
            if t is None:
                return m.group(0)
            q = m.group("q")
            return f'{m.group("pre")}{q}{t}{q}'  # keep the original quotes (or their absence)
        text = ATTR_RX.sub(attr, text)
        text = CSS_URL_RX.sub(lambda m: f'url({m.group(1)}{self.target(base_url, m.group(2), page_rel) or m.group(2)}{m.group(1)})', text)
        text = ABS_RX.sub(lambda m: self.target(base_url, m.group(0), page_rel) or m.group(0), text)
        text = SCRIPT_RX.sub(lambda m: m.group(1) + self.fix_rootrel_js(m.group(2), base_url) + m.group(3), text)
        # Third-party dependencies that no longer exist (Sony Music toolbars, counters, ads):
        # external scripts are dropped; external images are requested from the Internet Archive.
        live_cdn = ("ajax.googleapis.com", "code.jquery.com", "cdnjs.cloudflare.com", "ajax.aspnetcdn.com")
        text = EXT_SCRIPT_RX.sub(lambda m: m.group(0) if urllib.parse.urlsplit(m.group(1)).netloc.lower() in live_cdn
                                 else f"<!-- {raw_fixes.MARK}: external script removed: {m.group(1)} -->", text)

        def ext_img(m):
            u = m.group("url")
            if not ext_of(u).endswith(IMG_EXT) or "web.archive.org" in u:
                return m.group(0)
            q = m.group("q")
            return f'{m.group("pre")}{q}https://web.archive.org/web/{self.ts or "2004"}im_/{u}{q}'
        text = EXT_IMG_RX.sub(ext_img, text)
        if re.search(r"<frameset\b", text, re.I):
            # a frameset has no <body>: Ruffle fails there; every frame loads its own Ruffle
            if "Shockwave Flash'" not in text:
                mh = re.search(r"<head[^>]*>", text, re.I)
                text = (text[:mh.end()] + FLASH_SHIM + text[mh.end():]) if mh else FLASH_SHIM + text
        elif "ruffle.js" not in text:
            # The shim goes first: period Flash detectors run before Ruffle registers its plugin.
            inject = (FLASH_SHIM + f'<script src="{root}_ruffle/rewrite.js"></script>'
                      '<script>window.RufflePlayer=window.RufflePlayer||{};window.RufflePlayer.config={autoplay:"on",unmuteOverlay:"hidden",'
                      'warnOnUnsupportedContent:false,contextMenu:"off",letterbox:"on",allowScriptAccess:true,'
                      'urlRewriteRules:window.GTAWEB_REWRITE||[]};</script>'
                      f'<script src="{root}_ruffle/ruffle.js"></script>')
            mh = re.search(r"<head[^>]*>", text, re.I)
            if mh:
                text = text[:mh.end()] + inject + text[mh.end():]
            else:
                mt = re.search(r"<html[^>]*>", text, re.I)
                text = (text[:mt.end()] + inject + text[mt.end():]) if mt else inject + text
        return text

    def rewrite_text(self, text, base_url, page_rel, is_js):
        text = ABS_RX.sub(lambda m: self.target(base_url, m.group(0), page_rel) or m.group(0), text)
        return self.fix_rootrel_js(text, base_url) if is_js else text


class Page:
    """What a raw_fixes rule may ask about the page it repairs: its URL, its site, and
    whether the mirror has another file (ctx.have) and its original bytes (ctx.read).
    Only files downloaded into the cache count; there is no fallback to the other copy
    of a twin site (that is what raw_fixes.twins decides)."""

    def __init__(self, url, site, url_map, qless, cache):
        self.url, self.site = url, site
        self._map, self._qless, self._cache = url_map, qless, cache

    def _file(self, u, base=None):
        u = WAYBACK_RX.sub("", (u or "").strip())
        if not u or u.startswith(("#", "javascript:", "mailto:", "data:", "about:")):
            return None
        absu = urllib.parse.urljoin(urllib.parse.urljoin(self.url, base) if base else self.url, u).split("#")[0]
        if not absu.startswith("http"):
            return None
        key = Rewriter.norm(absu)
        base_key, _, query = key.partition("?")
        hit = self._map.get(key)
        if hit is None and not base_key.endswith("/"):
            hit = self._map.get(base_key + "/" + (f"?{query}" if query else ""))
        if hit is None and query:
            hit = self._qless.get(base_key)
        if hit is None:
            return None
        f = self._cache / hit[0] / "_raw" / hit[1]
        return f if f.is_file() else None

    def have(self, u, base=None):
        return self._file(u, base) is not None

    def read(self, u, base=None):
        f = self._file(u, base)
        return f.read_bytes() if f else None


# ------------------------------------------------------------------ manifests and locks


def load_manifests(cache):
    ms = []
    for man in sorted(cache.glob("*/_manifest/*.json")):
        m = json.loads(man.read_text(encoding="utf-8"))
        m["_path"] = man
        ms.append(m)
    return ms


def save_manifest(m):
    m["_path"].write_text(json.dumps({k: v for k, v in m.items() if k != "_path"}, indent=1), encoding="utf-8")


def build_maps(manifests):
    """URL -> (game, path). The site whose prefix contains the URL (its owner) wins."""
    url_map, qless, dir_game = {}, {}, {}
    for owner_pass in (True, False):
        for m in manifests:
            s = m["site"]
            for r in m["rows"]:
                if owner_pass and not any(under_prefix(r["url"], p) for p in s["prefixes"]):
                    continue
                key = Rewriter.norm(r["url"])
                val = (s["game"], local_rel(r["url"], r["mime"]))
                url_map.setdefault(key, val)
                if "?" in key:
                    qless.setdefault(key.split("?")[0], val)
                parts = key.split("?")[0].split("/")
                for i in range(1, len(parts)):
                    dir_game.setdefault("/".join(parts[:i]).lower() + "/", s["game"])
    return url_map, qless, dir_game


def read_lock(lock_dir, sid):
    if not lock_dir:
        return None
    f = Path(lock_dir) / f"{sid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def write_lock(lock_dir, m):
    lock_dir = Path(lock_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    rows = [{k: r[k] for k in ROW_KEYS if k in r} for r in m["rows"]]
    data = {"site": m["site"]["id"], "rows": rows}
    if m.get("pruned"):
        data["pruned"] = m["pruned"]
    (lock_dir / f'{m["site"]["id"]}.json').write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def list_site(net, s, lock, refresh, assets_pass):
    """Rows of a site: from the lock, or from the CDX API (merged with the lock when refreshing)."""
    if lock and not refresh:
        return [dict(r) for r in lock["rows"]], 0
    rows = {}
    for pre in s["prefixes"]:
        rows.update(cdx_list(net, pre, s["from"], s["to"]))
    keep = [r for r in rows.values() if wanted(r)]
    skipped = len(rows) - len(keep)
    if assets_pass:
        have = {Rewriter.norm(r["url"]) for r in keep}
        for pre in s["prefixes"]:
            for r in cdx_list(net, pre, s["from"], "", non_html_only=True).values():
                if wanted(r) and Rewriter.norm(r["url"]) not in have:
                    have.add(Rewriter.norm(r["url"]))
                    keep.append(r)
    if lock:
        pruned = {Rewriter.norm(p["url"]) for p in lock.get("pruned", [])}
        keep = [r for r in keep if Rewriter.norm(r["url"]) not in pruned]
        have = {Rewriter.norm(r["url"]) for r in keep}
        keep += [dict(r) for r in lock["rows"] if Rewriter.norm(r["url"]) not in have]  # rows added by hand
    return keep, skipped


def download(net, s, r, raw):
    """Fetch one row into raw. The pinned capture first, then the site's time, then the row's."""
    tries = [r["cap"]] if r.get("cap") else []
    tries += [t for t in (s["ts"], r["ts"]) if t not in tries]
    for ts in tries:
        st, final, _, body = net.get(f'https://web.archive.org/web/{ts}id_/{r["url"]}')
        if st == 200 and body and len(body) <= MAX_BYTES and body_ok(r["url"], body) and same_resource(final, r["url"]):
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(body)
            return capture_of(final) or ts, hashlib.sha1(body).hexdigest()
    return None, None


# ------------------------------------------------------------------ main


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mirror archived sites from the Wayback Machine for local browsing.")
    ap.add_argument("sites")
    ap.add_argument("out")
    ap.add_argument("--cache", help="folder for _raw/ and _manifest/ (default: <out>)")
    ap.add_argument("--lock", help="folder with the lock files (<id>.json)")
    ap.add_argument("--only", default="")
    ap.add_argument("--delay", type=float, default=0.8, help="seconds between the requests of each download worker")
    ap.add_argument("--workers", type=int, default=1, help="parallel downloads (default 1; the Archive refuses connections when asked too fast)")
    ap.add_argument("--rewrite-only", action="store_true", help="only rewrite from the cache, no network")
    ap.add_argument("--refresh", action="store_true", help="list locked sites from the CDX API again")
    ap.add_argument("--assets-pass", action="store_true", help="also list non-HTML resources captured after the window")
    ap.add_argument("--externals", action="store_true", help="copy the scripts/CSS/images the pages load from other hosts")
    ap.add_argument("--write-lock", help="write lock files for the processed sites into this folder")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sites = json.loads(Path(a.sites).read_text(encoding="utf-8"))
    only = set(x for x in a.only.split(",") if x)
    out = Path(a.out)
    cache = Path(a.cache) if a.cache else out
    net = Net(a.delay)
    stats = {"downloaded": 0, "failed": 0, "changed": [], "fixed": 0}

    # 1) list
    for s in sites:
        if only and s["id"] not in only:
            continue
        man = cache / s["game"] / "_manifest" / f'{s["id"]}.json'
        lock = read_lock(a.lock, s["id"])
        from_lock = lock and not a.refresh
        # a lock file is the source of truth: the manifest is written again from it on
        # every build (no network); without one, a manifest is only listed once
        if not from_lock and man.exists() and not (a.refresh or a.assets_pass):
            continue
        if a.rewrite_only and not from_lock:
            continue
        rows, skipped = list_site(net, s, lock, a.refresh, a.assets_pass)
        if man.exists():  # keep what is known about downloaded captures the lock does not pin
            old = {Rewriter.norm(r["url"]): r for r in json.loads(man.read_text(encoding="utf-8"))["rows"]}
            for r in rows:
                o = old.get(Rewriter.norm(r["url"]))
                if o and not r.get("cap") and o.get("cap"):
                    r["cap"], r["sha1"] = o["cap"], o.get("sha1")
        m = {"site": s, "rows": rows, "skipped": skipped}
        if lock and lock.get("pruned"):
            m["pruned"] = lock["pruned"]
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps(m, indent=1), encoding="utf-8")
        print(f'[{s["game"]}] {s["id"]}: {len(rows)} files ({"lock" if lock and not a.refresh else "CDX"})', flush=True)

    manifests = load_manifests(cache)
    # drop rows outside the prefix (SURT sweep) or that are errors under image URLs
    # ("ext" rows are external dependencies the pages load, and are kept)
    for m in manifests:
        s = m["site"]
        if only and s["id"] not in only:
            continue
        before = len(m["rows"])
        m["rows"] = [r for r in m["rows"] if wanted(r) and (r.get("ext") or any(under_prefix(r["url"], p) for p in s["prefixes"]))]
        if len(m["rows"]) != before:
            save_manifest(m)
            print(f'[{s["game"]}] {s["id"]}: {before - len(m["rows"])} rows outside the prefix or invalid', flush=True)
    url_map, qless, dir_game = build_maps(manifests)

    # 1b) external dependencies the pages LOAD (scripts, CSS, images, SWF from other hosts,
    #     e.g. jQuery on media.rockstargames.com): copied from the Archive, recorded in the site.
    if a.externals and not a.rewrite_only:
        dep_rx = re.compile(r'''<(?:script|img|embed|input|link|body|td|table)\b[^>]*?\b(?:src|href|background)\s*=\s*["']?(https?://[^"'\s>]+)''', re.I)
        param_rx = re.compile(r'''<param\b[^>]*value\s*=\s*["']?(https?://[^"'\s>]+\.swf)''', re.I)
        for m in manifests:
            s = m["site"]
            if only and s["id"] not in only:
                continue
            gdir = cache / s["game"]
            found = {}
            for r in m["rows"]:
                raw = gdir / "_raw" / local_rel(r["url"], r["mime"])
                if not raw.exists() or not ("html" in r["mime"] or raw.suffix.lower() in (".html", ".htm")):
                    continue
                text = raw.read_text(encoding="latin-1")
                for u in dep_rx.findall(text) + param_rx.findall(text):
                    u = WAYBACK_RX.sub("", u)
                    ext = ext_of(u)
                    if ext not in (".js", ".css", ".gif", ".jpg", ".jpeg", ".png", ".swf"):
                        continue  # <link>/<a> to pages are not dependencies
                    if Rewriter.norm(u) in url_map or "web.archive.org" in u:
                        continue
                    found.setdefault(Rewriter.norm(u), u)
            add = 0
            for key, u in found.items():
                row = {"ts": s["ts"], "url": u, "mime": "application/javascript" if u.lower().endswith(".js") else
                       "text/css" if u.lower().endswith(".css") else "application/octet-stream", "len": 0, "ext": True}
                raw = gdir / "_raw" / local_rel(u, row["mime"])
                if not raw.exists():
                    cap, sha1 = download(net, s, row, raw)
                    if not cap:
                        continue
                    row["cap"], row["sha1"] = cap, sha1
                m["rows"].append(row)
                url_map.setdefault(key, (s["game"], local_rel(u, row["mime"])))
                add += 1
            if add:
                save_manifest(m)
            print(f'[{s["game"]}] {s["id"]}: {add} external dependencies copied out of {len(found)} found', flush=True)
        url_map, qless, dir_game = build_maps(manifests)

    # 2) download (pinned capture, then the site's time, then the row's own capture),
    #    a few files at a time; every worker keeps --delay between its own requests
    if not a.rewrite_only:
        tasks, dupes, first = [], [], {}
        for m in manifests:
            s = m["site"]
            if only and s["id"] not in only:
                continue
            gdir = cache / s["game"]
            lock = read_lock(a.lock, s["id"])
            expected = {Rewriter.norm(r["url"]): r.get("sha1") for r in (lock or {}).get("rows", [])}
            for r in m["rows"]:
                rel = local_rel(r["url"], r["mime"])
                raw = gdir / "_raw" / rel
                want = expected.get(Rewriter.norm(r["url"]))
                # cached files are kept, unless the lock pins other bytes (a capture changed in the lock)
                if raw.exists() and (not want or hashlib.sha1(raw.read_bytes()).hexdigest() == want):
                    continue
                t = (m, s, r, rel, raw, want)
                key = str(raw).lower()
                if key in first:  # the same file listed twice: download it once
                    dupes.append((t, first[key]))
                else:
                    first[key] = t
                    tasks.append(t)
        local = threading.local()

        def work(t):
            if not hasattr(local, "net"):
                local.net = Net(a.delay)
            m, s, r, rel, raw, want = t
            return download(local.net, s, r, raw)

        per_site, dirty = {}, set()
        # The Archive sometimes answers 404 or an error page for a capture it does have
        # (a storage node is busy): what failed is tried again, twice, after a pause.
        todo = tasks
        for attempt in range(3):
            if not todo:
                break
            if attempt:
                print(f"  trying {len(todo)} failed files again in 30 s", flush=True)
                time.sleep(30)
            failed, done = [], 0
            with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
                for t, (cap, sha1) in zip(todo, pool.map(work, todo)):
                    m, s, r, rel, raw, want = t
                    ok_miss = per_site.setdefault(s["id"], [s["game"], 0, 0])
                    done += 1
                    if cap:
                        ok_miss[1] += 1
                        r["cap"], r["sha1"] = cap, sha1
                        dirty.add(id(m))
                        if want and want != sha1:
                            stats["changed"].append(f'{s["game"]}/{rel}')
                    else:
                        failed.append(t)
                    if done % 25 == 0:
                        print(f"  {done}/{len(todo)} files", flush=True)
                        for mm in manifests:
                            if id(mm) in dirty:
                                save_manifest(mm)
            todo = failed
        for t in todo:
            per_site.setdefault(t[1]["id"], [t[1]["game"], 0, 0])[2] += 1
        for t, src in dupes:
            if src[2].get("cap"):
                t[2]["cap"], t[2]["sha1"] = src[2]["cap"], src[2]["sha1"]
                dirty.add(id(t[0]))
        for mm in manifests:
            if id(mm) in dirty:
                save_manifest(mm)
        for sid, (game, got, miss) in per_site.items():
            stats["downloaded"] += got
            stats["failed"] += miss
            print(f'[{game}] {sid}: downloaded {got}, failed {miss}', flush=True)

    # 3) repair + rewrite (always from _raw)
    for m in manifests:
        s = m["site"]
        if only and s["id"] not in only:
            continue
        gdir = cache / s["game"]
        odir = out / s["game"]
        rw = Rewriter(url_map, qless, dir_game, s["game"], s["prefixes"], s["ts"])
        for r in m["rows"]:
            rel = local_rel(r["url"], r["mime"])
            raw = gdir / "_raw" / rel
            if not raw.exists():
                continue
            dst = odir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            body = raw.read_bytes()
            mime = r["mime"].lower()
            low = rel.lower().split("__")[0] if "__" in rel else rel.lower()
            is_html = "html" in mime or low.endswith(HTML_EXT) or rel.lower().endswith(HTML_EXT)
            if is_html:
                fixed = raw_fixes.apply(Page(r["url"], s, url_map, qless, cache), body)
                if fixed != body:
                    stats["fixed"] += 1
                    body = fixed
            if is_html or rel.lower().endswith(TEXT_EXT) or mime.startswith(("text/", "application/x-javascript", "application/javascript")):
                text = body.decode("latin-1")
                root = "../" * (rel.count("/") + 1)
                if is_html:
                    text = rw.rewrite_html(text, r["url"], rel, root)
                else:
                    text = rw.rewrite_text(text, r["url"], rel, rel.lower().endswith(".js") or "javascript" in mime)
                body = text.encode("latin-1")
            dst.write_bytes(body)

    # 4) remove served files that no longer belong to any site (full runs only)
    if not only:
        keep = {}
        for m in manifests:
            g = m["site"]["game"]
            keep.setdefault(g, set()).update(local_rel(r["url"], r["mime"]).lower() for r in m["rows"])
        removed = 0
        for g, rels in keep.items():
            gdir = out / g
            if not gdir.exists():
                continue
            for f in gdir.rglob("*"):
                if not f.is_file():
                    continue
                parts = f.relative_to(gdir).parts
                if parts[0] in ("_raw", "_manifest") or parts[0].startswith("_"):
                    continue
                if "/".join(parts).lower() not in rels:
                    f.unlink()
                    removed += 1
        if removed:
            print(f"cleanup: {removed} served files no longer belong to any site", flush=True)

    if a.write_lock:
        for m in manifests:
            if not only or m["site"]["id"] in only:
                write_lock(a.write_lock, m)
        print(f"lock files written to {a.write_lock}", flush=True)
    print(f'done: {stats["downloaded"]} downloaded, {stats["failed"]} not available, {stats["fixed"]} files repaired by raw_fixes', flush=True)
    if stats["changed"]:
        print(f'{len(stats["changed"])} files differ from the lock (the Archive serves different bytes today):', flush=True)
        for c in stats["changed"][:50]:
            print("  " + c, flush=True)
    return stats


if __name__ == "__main__":
    main()
