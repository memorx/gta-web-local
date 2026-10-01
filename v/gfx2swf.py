#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gfx2swf.py - converts GTA V Scaleform GFx movies into standard SWF files that Ruffle plays.

Normal use (one in-game web site):

    python gfx2swf.py <in.gfx> <png_textures_of_the_site_ytd> <out.swf> [--shared-png-root DIR]

    <png_textures_of_the_site_ytd>  folder with the PNGs of that site's .ytd
                                    (e.g. <work>/v/extract/png/www_bawsaq_com); "-" if none.

Other modes:

    python gfx2swf.py --build-fontlib <out/gfxfontlib.swf>
        Builds the combined font library that resolves the ImportAssets2 of
        "gfxfontlib.swf" the way the game does: every alias "$Font2", "$WebFont1_Hbold"...
        is resolved to the real font (font_lib_efigs, font_lib_web, gfxfontlib).  Only
        needed with --fonts import.

    python gfx2swf.py font_lib_web.gfx - font_lib_web.swf
        "As is" conversion of any .gfx (font libraries too).

What it does (details in each function):
  1. Container: GFX->FWS, CFX->CWS (zlib), keeps the version, re-serialises every tag
     (short/long headers) and recomputes FileLength.
  2. DefineExternalImage2 (1009), DefineExternalImage (1001) and DefineSubImage (1008)
     -> DefineBitsLossless2 (36, format 5, premultiplied ARGB, zlib) with the SAME
     character id.  The texture is looked up by fileName/exportName (lower case, no .dds)
     in the site folder, then under --shared-png-root; without a PNG (A8 textures) the DDS
     is decoded directly.  It is scaled to targetWidth x targetHeight.
  3. The original ExportAssets are kept; an export is added for images that had none.
  4. DefineExternalGradient (1003), DefineGradientMap (1004), FontTextureInfo (1002),
     ExporterInfo (1000): dropped.  Gradient fills stay inside the shapes (DefineShape*),
     so Ruffle draws them the same; 1003 was only a pre-rendered texture of that gradient.
  5. DefineCompactedFont (1005) -> DefineFont3 (75) with outlines, advances, ascent,
     descent, leading and kerning (format documented in JPEXS: FontType/GlyphType/
     ContourType/EdgeType).  Same id and glyph order (DefineText uses indices).  Every
     GFx font of the game uses nominalSize=256 -> exact x80 scale to the 20480 em of
     DefineFont3.  If an advance does not fit in SI16 (Chalet has 3 glyphs of 3 em)
     DefineFont2 is written instead (em 1024, x4, just as exact).
  6. ImportAssets2 of "gfxfontlib.swf": by default (--fonts inline) it is replaced by the
     real fonts embedded with the same ids, resolved as the game does (alias -> font
     library family).  The resulting SWF does not depend on any other file.
     With --fonts import the ImportAssets2 is kept; Ruffle resolves that relative URL
     against the "base" parameter of its config (NOT against the SWF URL): with base
     "/v/" it asks for "/v/gfxfontlib.swf".  That file is made with --build-fontlib.
  7. Font names: the game resolves <font face="..."> and TextFormat.font by name through
     the loaded font libraries.  To imitate it, when the SWF mentions a font name (real
     family or "$..." alias) it does not define, a copy of the right font is added under
     that name (new id).  None of the 82 files needs it, but it stays for other movies.
  8. DefineEditText: GFx has no device fonts, so fields without useOutlines whose font
     has glyphs are switched to use them (80 fields); unnamed fonts get a synthetic name
     "gfxfont_<id>" and the face="" of their initial HTML is changed to it (283 cases),
     because Ruffle looks fonts up by name.  Never forced on a font without layout:
     Ruffle would lay it out with zero width.
  9. GFx fonts without layout (no FF_HasLayout 0x2000: ascent/descent/leading and
     advances are 0).  There are 4 in the 97 movies: altruistsunite id 10
     "HelveticaNeueLT W1G 55 Roman" (its 11 Morse fields, device text in the original),
     classicvinewood 134 and suemurry (update) 36 "Chalet-LondonNineteenSixty",
     yourdeadfamily 41 (unnamed); the last three are only used by DefineText.  The game
     lays those fields out with the family it finds by name in the font libraries, so the
     layout of that copy is borrowed (same family and style; unnamed: the one with the
     same outlines): ascent, descent, leading, advance per code and kerning.  Glyphs the
     copy lacks get an advance estimated from their box (xmax + xmin).  See
     synthesize_layout / layout_donor.
 10. letterSpacing of the initial HTML of the fields: GFx applies only the integer part,
     towards zero (0.5 -> 0, -0.1/-0.3/-0.4 -> 0, -1 -> -1; measured against wiki
     screenshots of several sites: neither floor nor the fractional value give the game's
     lines).  Ruffle would apply the fraction: the truncated value is written.  -0.6 (a
     single site, the only value with a fraction > .5 in the 664 movies of the game) is
     left at 0 like the rest.
 11. wordWrap fields: Ruffle decides whether a word fits by measuring "word + space" and
     GFx/Flash without the space, so Ruffle breaks earlier (one word per line of
     difference, sometimes one more line that the field clips).  The field is widened by
     what a space measures in its dominant format (font, size) plus 2 x letterSpacing
     (GFx only puts it between glyphs, Ruffle also after the last one and in the space),
     towards the side that does not move the text given its alignment; with that Ruffle's
     rule gives the game's lines.  So that the last word of each paragraph (which Ruffle
     measures without the space) does not gain slack, static left/justified paragraphs get
     an invisible trailing space.  Fields with border/background are not touched.  See
     convert_edit_text.
     Measurements: GFx rounds every advance to the twip and puts letterSpacing only between
     glyphs; Ruffle truncates and puts it after every glyph (TextMetrics, fitted against 19
     wiki paragraphs).  With single-format initial text the exact width for which Ruffle
     gives the same lines as the game is computed (ruffle_width_interval).  If the script
     puts known GXT labels in the field (instance name = label, SET_TEXT_WITH_TRANSLATION
     or setLocalisedText read from the bytecode; texts from the same tables the host uses)
     the same computation is made with those texts.  With no known text, the robust point:
     one space minus the expected rounding bias of a full line (robust_wrap_extra).
     Fields whose box the AS reads or writes (_width, getBounds; _x if widening moves the
     left edge): the smallest widening that gives the game's lines (0 for single-line or
     unknown text), because the game places or sizes other things with that box (photos of
     the vehicle catalogues: <img> of vehicleImage._width - 4).  And inside clips whose box
     the AS reads, without leaving that box.  See _wrap_extra_twips.
 12. GFx does not draw a line that does not fit entirely in the field height; Ruffle draws
     it clipped.  In static text with the lines already computed, the field height is
     lowered to the top of that line.
 13. U+00A0: almost no font has it; Ruffle draws it zero wide and GFx half an em (measured
     on wiki screenshots): an empty glyph is added (ensure_nbsp_glyph).

Images: DefineBitsLossless2 by default (lossless).  --image-format png uses DefineBitsJPEG2
with a PNG inside: identical in Ruffle but larger in practice.

Only needs Python 3.9+ and Pillow.  (Code comments are in Spanish, the language the tool was
written in.)
"""

from __future__ import annotations

import argparse
import html as _html
import io
import math
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("gfx2swf.py needs Pillow (pip install pillow)")


# ---------------------------------------------------------------------------
# Default paths: <work>/v/extract and <work>/v/text of the repository config.toml
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
def _default_work_v() -> str:
    """<work>/v from the repository config.toml (common/config.py); "work/v" if unavailable."""
    try:
        sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
        from common.config import load_config
        return str(load_config().work / "v")
    except Exception:  # pragma: no cover
        return os.path.join("work", "v")


WORK_V = _default_work_v()
DEFAULT_EXTRACT = os.path.join(WORK_V, "extract")

# Font libs en orden de preferencia (la version de update primero).
FONT_LIB_CANDIDATES = [
    "gen_update/x64/data/cdimages/generic/font_lib_efigs.gfx",
    "gen_x64b/data/cdimages/generic/font_lib_efigs.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_web.gfx",
    "gen_x64b/data/cdimages/generic/font_lib_web.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_heists.gfx",
    "gen_x64b/data/cdimages/generic/font_lib_heists.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_org.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_slots.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_taxi.gfx",
    "gen_update/x64/data/cdimages/generic/font_lib_typewriter.gfx",
    # gfxfontlib.gfx es la libreria "de autor" (placeholders de Flash): ultima opcion.
    "common/data/scaleform/gfxfontlib.gfx",
]
FONTMAP_CANDIDATES = [
    "upd_ui/common/data/ui/fontmap.xml",
    "common/data/ui/fontmap.xml",
]
# Nombres de URL que el juego trata como "biblioteca de fuentes del sistema".
FONTLIB_URLS = {"gfxfontlib.swf", "gfxfontlib.gfx"}

# ---------------------------------------------------------------------------
# Codigos de etiqueta
# ---------------------------------------------------------------------------
T_END = 0
T_SHOWFRAME = 1
T_DEFINEFONT2 = 48
T_DEFINEFONT3 = 75
T_EXPORTASSETS = 56
T_IMPORTASSETS = 57
T_IMPORTASSETS2 = 71
T_DEFINESPRITE = 39
T_DEFINEEDITTEXT = 37
T_DEFINEBITSJPEG2 = 21
T_DEFINEBITSLOSSLESS2 = 36
T_DOACTION = 12
T_DOINITACTION = 59

GFX_EXPORTERINFO = 1000
GFX_DEFINEEXTERNALIMAGE = 1001
GFX_FONTTEXTUREINFO = 1002
GFX_DEFINEEXTERNALGRADIENT = 1003
GFX_DEFINEGRADIENTMAP = 1004
GFX_DEFINECOMPACTEDFONT = 1005
GFX_DEFINEEXTERNALSOUND = 1006
GFX_DEFINEEXTERNALSTREAMSOUND = 1007
GFX_DEFINESUBIMAGE = 1008
GFX_DEFINEEXTERNALIMAGE2 = 1009

# Flags de FontType (Scaleform Render::Font::FontFlags).  0x4000 = WideCodes.
GFX_FF_ITALIC = 0x0001
GFX_FF_BOLD = 0x0002
GFX_FF_HASLAYOUT = 0x2000

# Etiquetas "Define*" cuyo primer UI16 es el id de caracter (para buscar ids libres).
DEFINE_TAGS = {2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37, 39, 46, 48,
               60, 75, 83, 84, 87, 90, 91,
               GFX_DEFINEEXTERNALIMAGE, GFX_DEFINECOMPACTEDFONT, GFX_DEFINESUBIMAGE,
               GFX_DEFINEEXTERNALIMAGE2}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ===========================================================================
# 1. Contenedor SWF / GFx
# ===========================================================================
@dataclass
class Tag:
    code: int
    data: bytes


@dataclass
class Movie:
    signature: bytes          # b"GFX", b"CFX", b"FWS", b"CWS"
    version: int
    rect: bytes               # RECT del escenario, bytes tal cual
    frame_rate: int           # UI16 8.8 tal cual
    frame_count: int
    tags: List[Tag]


def rect_nbytes(buf: bytes, pos: int = 0) -> int:
    nbits = buf[pos] >> 3
    return (5 + 4 * nbits + 7) // 8


def parse_tags(buf: bytes, pos: int, end: int) -> List[Tag]:
    """Lee etiquetas (cabecera corta o larga) hasta End o fin del buffer."""
    tags: List[Tag] = []
    while pos + 2 <= end:
        (hdr,) = struct.unpack_from("<H", buf, pos)
        pos += 2
        code, length = hdr >> 6, hdr & 0x3F
        if length == 0x3F:
            (length,) = struct.unpack_from("<I", buf, pos)
            pos += 4
        if pos + length > end:
            raise ValueError("tag %d truncated at offset %d" % (code, pos))
        tags.append(Tag(code, bytes(buf[pos:pos + length])))
        pos += length
        if code == T_END:
            break
    return tags


# Etiquetas que Flash siempre escribe con cabecera larga (algunos lectores lo esperan).
ALWAYS_LONG = {6, 20, 21, 35, 36, 90}


def encode_tag(code: int, data: bytes) -> bytes:
    if len(data) < 0x3F and code not in ALWAYS_LONG:
        return struct.pack("<H", (code << 6) | len(data)) + data
    return struct.pack("<HI", (code << 6) | 0x3F, len(data)) + data


def encode_tags(tags: Iterable[Tag]) -> bytes:
    return b"".join(encode_tag(t.code, t.data) for t in tags)


def read_movie(raw: bytes) -> Movie:
    sig = raw[:3]
    if sig not in (b"GFX", b"CFX", b"FWS", b"CWS"):
        raise ValueError("not a GFx/SWF file (signature %r)" % sig)
    version = raw[3]
    (file_len,) = struct.unpack_from("<I", raw, 4)
    body = raw[8:]
    if sig in (b"CFX", b"CWS"):
        body = zlib.decompress(body)
    if len(body) + 8 != file_len:
        log("  warning: header FileLength %d != actual %d" % (file_len, len(body) + 8))
    rl = rect_nbytes(body)
    rect = body[:rl]
    frame_rate, frame_count = struct.unpack_from("<HH", body, rl)
    tags = parse_tags(body, rl + 4, len(body))
    return Movie(sig, version, rect, frame_rate, frame_count, tags)


def write_movie(movie: Movie, compress: bool) -> bytes:
    tags = list(movie.tags)
    if not tags or tags[-1].code != T_END:
        tags.append(Tag(T_END, b""))
    body = movie.rect + struct.pack("<HH", movie.frame_rate, movie.frame_count) + encode_tags(tags)
    file_len = len(body) + 8
    if compress:
        return b"CWS" + bytes([movie.version]) + struct.pack("<I", file_len) + zlib.compress(body, 9)
    return b"FWS" + bytes([movie.version]) + struct.pack("<I", file_len) + body


def split_sprite(data: bytes) -> Tuple[int, int, List[Tag]]:
    sprite_id, frames = struct.unpack_from("<HH", data, 0)
    return sprite_id, frames, parse_tags(data, 4, len(data))


def join_sprite(sprite_id: int, frames: int, tags: List[Tag]) -> bytes:
    return struct.pack("<HH", sprite_id, frames) + encode_tags(tags)


def read_cstr(buf: bytes, pos: int) -> Tuple[str, int]:
    end = buf.index(b"\0", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


def read_netstr(buf: bytes, pos: int) -> Tuple[str, int]:
    n = buf[pos]
    return buf[pos + 1:pos + 1 + n].decode("utf-8", "replace"), pos + 1 + n


def parse_export_assets(data: bytes) -> List[Tuple[int, str]]:
    (count,) = struct.unpack_from("<H", data, 0)
    pos, out = 2, []
    for _ in range(count):
        (cid,) = struct.unpack_from("<H", data, pos)
        name, pos = read_cstr(data, pos + 2)
        out.append((cid, name))
    return out


def encode_export_assets(items: List[Tuple[int, str]]) -> bytes:
    out = bytearray(struct.pack("<H", len(items)))
    for cid, name in items:
        out += struct.pack("<H", cid) + name.encode("utf-8") + b"\0"
    return bytes(out)


def parse_import_assets(code: int, data: bytes) -> Tuple[str, bytes, List[Tuple[int, str]]]:
    """Devuelve (url, bytes_reservados, [(id, nombre)])."""
    url, pos = read_cstr(data, 0)
    reserved = b""
    if code == T_IMPORTASSETS2:
        reserved = data[pos:pos + 2]
        pos += 2
    (count,) = struct.unpack_from("<H", data, pos)
    pos += 2
    items = []
    for _ in range(count):
        (cid,) = struct.unpack_from("<H", data, pos)
        name, pos = read_cstr(data, pos + 2)
        items.append((cid, name))
    return url, reserved, items


def encode_import_assets(code: int, url: str, reserved: bytes, items: List[Tuple[int, str]]) -> bytes:
    out = bytearray(url.encode("utf-8") + b"\0")
    if code == T_IMPORTASSETS2:
        out += reserved or b"\x01\x00"
    out += struct.pack("<H", len(items))
    for cid, name in items:
        out += struct.pack("<H", cid) + name.encode("utf-8") + b"\0"
    return bytes(out)


# ===========================================================================
# Escritor de bits (RECT, SHAPE)
# ===========================================================================
class BitWriter:
    def __init__(self) -> None:
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def ub(self, nbits: int, value: int) -> None:
        for i in range(nbits - 1, -1, -1):
            self.acc = (self.acc << 1) | ((value >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = 0
                self.n = 0

    def sb(self, nbits: int, value: int) -> None:
        self.ub(nbits, value & ((1 << nbits) - 1))

    def align(self) -> None:
        if self.n:
            self.out.append(self.acc << (8 - self.n))
            self.acc = 0
            self.n = 0

    def getvalue(self) -> bytes:
        self.align()
        return bytes(self.out)


def sbits(*values: int) -> int:
    """Bits necesarios para representar todos los valores como enteros con signo."""
    n = 1
    for v in values:
        v = int(v)
        need = (v.bit_length() + 1) if v >= 0 else ((~v).bit_length() + 1)
        n = max(n, need)
    return n


def encode_rect(xmin: int, xmax: int, ymin: int, ymax: int) -> bytes:
    bw = BitWriter()
    nb = sbits(xmin, xmax, ymin, ymax)
    bw.ub(5, nb)
    for v in (xmin, xmax, ymin, ymax):
        bw.sb(nb, v)
    return bw.getvalue()


def decode_rect(buf: bytes, pos: int = 0) -> Tuple[int, int, int, int]:
    """RECT -> (xmin, xmax, ymin, ymax) en twips."""
    nb = buf[pos] >> 3
    size = rect_nbytes(buf, pos)
    bits = int.from_bytes(buf[pos:pos + size], "big")
    total = size * 8
    vals = []
    for i in range(4):
        v = (bits >> (total - 5 - nb * (i + 1))) & ((1 << nb) - 1) if nb else 0
        if nb and v >> (nb - 1):
            v -= 1 << nb
        vals.append(v)
    return vals[0], vals[1], vals[2], vals[3]


# ===========================================================================
# 2. Texturas -> DefineBitsLossless2
# ===========================================================================
def load_dds(path: str) -> Image.Image:
    """Carga un DDS.  Formatos sin comprimir (A8, L8, A8L8, ARGB/XRGB) se decodifican
    aqui; los comprimidos (DXT1/3/5) se delegan a Pillow."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:4] != b"DDS ":
        raise ValueError("not a DDS file: " + path)
    (hsize, flags, height, width, pitch) = struct.unpack_from("<5I", raw, 4)
    pf_flags, fourcc, bitcount, rmask, gmask, bmask, amask = struct.unpack_from("<I4s5I", raw, 80)
    data = raw[4 + hsize:]
    DDPF_ALPHA, DDPF_FOURCC, DDPF_RGB, DDPF_LUMINANCE = 0x2, 0x4, 0x40, 0x20000
    if not (pf_flags & DDPF_FOURCC):
        bpp = bitcount // 8
        row = pitch if (flags & 0x8) and pitch else width * bpp
        if pf_flags & DDPF_ALPHA and bitcount == 8 and not (pf_flags & (DDPF_RGB | DDPF_LUMINANCE)):
            # D3DFMT_A8: Direct3D devuelve (0,0,0,a) al muestrear.
            alpha = Image.frombytes("L", (width, height), data, "raw", "L", row)
            black = Image.new("L", (width, height), 0)
            return Image.merge("RGBA", (black, black, black, alpha))
        if pf_flags & DDPF_LUMINANCE and bitcount == 8:
            lum = Image.frombytes("L", (width, height), data, "raw", "L", row)
            return lum.convert("RGBA")
        if pf_flags & DDPF_LUMINANCE and bitcount == 16:
            la = Image.frombytes("LA", (width, height), data, "raw", "LA", row)
            return la.convert("RGBA")
        if pf_flags & DDPF_RGB and bitcount == 32:
            mode = "BGRA" if amask else "BGRX"
            img = Image.frombytes("RGBA", (width, height), data, "raw", mode, row)
            return img
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img.convert("RGBA")


class TextureResolver:
    """Encuentra la textura de una imagen externa.

    Orden: PNG del sitio -> DDS del sitio -> PNG compartidos -> DDS compartidos.
    La clave es el nombre de archivo (sin .dds) y, si no aparece, el exportName;
    siempre en minusculas (asi estan exportados los PNG)."""

    def __init__(self, site_png_dir: Optional[str], shared_png_root: Optional[str],
                 site_dds_dir: Optional[str] = None, shared_dds_root: Optional[str] = None):
        self.site_png_dir = site_png_dir if site_png_dir and os.path.isdir(site_png_dir) else None
        self.site_dds_dir = site_dds_dir or self._sibling_dds(self.site_png_dir)
        self.shared_png_root = shared_png_root if shared_png_root and os.path.isdir(shared_png_root) else None
        self.shared_dds_root = shared_dds_root or self._sibling_dds(self.shared_png_root)
        self._shared_png: Optional[Dict[str, List[str]]] = None
        self._shared_dds: Optional[Dict[str, List[str]]] = None

    @staticmethod
    def _sibling_dds(png_path: Optional[str]) -> Optional[str]:
        """<extract>/png/<ytd> -> <extract>/dds/<ytd> (same layout)."""
        if not png_path:
            return None
        parts = os.path.normpath(png_path).split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].lower() == "png":
                cand = os.sep.join(parts[:i] + ["dds"] + parts[i + 1:])
                return cand if os.path.isdir(cand) else None
        return None

    @staticmethod
    def _index(root: Optional[str], ext: str) -> Dict[str, List[str]]:
        idx: Dict[str, List[str]] = {}
        if not root:
            return idx
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith(ext):
                    idx.setdefault(fn[:-len(ext)].lower(), []).append(os.path.join(dirpath, fn))
        for v in idx.values():
            v.sort()
        return idx

    def _find_in_dir(self, d: Optional[str], key: str, ext: str) -> Optional[str]:
        if not d:
            return None
        p = os.path.join(d, key + ext)
        if os.path.isfile(p):
            return p
        # por si el nombre en disco conserva mayusculas
        try:
            for fn in os.listdir(d):
                if fn.lower() == key + ext:
                    return os.path.join(d, fn)
        except OSError:
            pass
        return None

    def resolve(self, keys: List[str]) -> Tuple[Optional[Image.Image], str]:
        keys = [k for k in dict.fromkeys(k.lower() for k in keys if k)]
        for key in keys:
            p = self._find_in_dir(self.site_png_dir, key, ".png")
            if p:
                return Image.open(p).convert("RGBA"), p
            p = self._find_in_dir(self.site_dds_dir, key, ".dds")
            if p:
                return load_dds(p), p
        if self.shared_png_root:
            if self._shared_png is None:
                self._shared_png = self._index(self.shared_png_root, ".png")
            for key in keys:
                if key in self._shared_png:
                    p = self._shared_png[key][0]
                    return Image.open(p).convert("RGBA"), p
        if self.shared_dds_root:
            if self._shared_dds is None:
                self._shared_dds = self._index(self.shared_dds_root, ".dds")
            for key in keys:
                if key in self._shared_dds:
                    p = self._shared_dds[key][0]
                    return load_dds(p), p
        return None, ""


def encode_lossless2(char_id: int, img: Image.Image) -> bytes:
    """DefineBitsLossless2, formato 5: ARGB premultiplicado, comprimido con zlib."""
    img = img.convert("RGBA")
    w, h = img.size
    r, g, b, a = img.convert("RGBa").split()          # RGBa = RGB premultiplicado
    argb = Image.merge("RGBA", (a, r, g, b)).tobytes()  # orden de bytes A,R,G,B
    return struct.pack("<HBHH", char_id, 5, w, h) + zlib.compress(argb, 9)


def encode_jpeg2_png(char_id: int, img: Image.Image) -> bytes:
    """DefineBitsJPEG2 con datos PNG (SWF8+).  Mas pequeno; alternativa opcional."""
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, "PNG", optimize=True)
    return struct.pack("<H", char_id) + buf.getvalue()


# ===========================================================================
# 3. Fuentes: DefineCompactedFont (GFx) -> DefineFont3
# ===========================================================================
@dataclass
class Glyph:
    code: int
    advance: int
    bbox: Tuple[int, int, int, int]              # xmin, ymin, xmax, ymax (unidades GFx)
    # contornos: (moveX, moveY, [edges]); edge = ('L', dx, dy) o ('Q', cx, cy, ax, ay)
    contours: List[Tuple[int, int, list]]


@dataclass
class FontData:
    """Fuente con contornos en unidades de 'nominal' por em (GFx: 256)."""
    name: str
    flags: int                 # bit0 italic, bit1 bold (GFx FF_Italic / FF_Bold)
    nominal: int
    ascent: int
    descent: int
    leading: int
    glyphs: List[Glyph] = field(default_factory=list)
    kerning: List[Tuple[int, int, int]] = field(default_factory=list)

    @property
    def italic(self) -> bool:
        return bool(self.flags & GFX_FF_ITALIC)

    @property
    def bold(self) -> bool:
        return bool(self.flags & GFX_FF_BOLD)

    @property
    def has_layout(self) -> bool:
        """Sin FF_HasLayout la fuente trae ascent/descent/leading = 0 y todos los avances
        a 0: solo sirve para DefineText (que lleva sus propios avances)."""
        return bool(self.flags & GFX_FF_HASLAYOUT)


class GfxReader:
    """Lectura de los enteros de longitud variable de GFx (ver GFxInputStream de JPEXS)."""

    def __init__(self, buf: bytes, pos: int = 0):
        self.buf = buf
        self.pos = pos

    def u8(self) -> int:
        v = self.buf[self.pos]
        self.pos += 1
        return v

    def s8(self) -> int:
        v = self.u8()
        return v - 256 if v >= 128 else v

    def u16(self) -> int:
        (v,) = struct.unpack_from("<H", self.buf, self.pos)
        self.pos += 2
        return v

    def s16(self) -> int:
        (v,) = struct.unpack_from("<h", self.buf, self.pos)
        self.pos += 2
        return v

    def u32(self) -> int:
        (v,) = struct.unpack_from("<I", self.buf, self.pos)
        self.pos += 4
        return v

    def cstr(self) -> str:
        end = self.buf.index(b"\0", self.pos)
        s = self.buf[self.pos:end].decode("utf-8", "replace")
        self.pos = end + 1
        return s

    def si15(self) -> int:
        t = self.s8()
        if (t & 1) == 0:
            return t >> 1
        t = (t >> 1) & 0x7F
        return t | (self.s8() << 7)

    def ui15(self) -> int:
        t = self.u8()
        if (t & 1) == 0:
            return t >> 1
        return (t >> 1) | (self.u8() << 7)

    def ui30(self) -> int:
        t = self.u8()
        kind = t & 3
        v = t >> 2
        if kind >= 1:
            v |= self.u8() << 6
        if kind >= 2:
            v |= self.u8() << 14
        if kind >= 3:
            v |= self.u8() << 22
        return v


# Tipos de arista del compactador de GFx: (bytes totales, tipo, ancho de cada campo).
# Todos los campos estan empaquetados en little-endian a partir del bit 4 y con signo.
_EDGE_FORMATS = {
    0: (2, "H", 12), 1: (3, "H", 20),
    2: (2, "V", 12), 3: (3, "V", 20),
    4: (2, "L", 6), 5: (3, "L", 10), 6: (4, "L", 14), 7: (5, "L", 18),
    8: (3, "Q", 5), 9: (4, "Q", 7), 10: (5, "Q", 9), 11: (6, "Q", 11),
    12: (7, "Q", 13), 13: (8, "Q", 15), 14: (9, "Q", 17), 15: (10, "Q", 19),
}


def _read_edge(rd: GfxReader) -> tuple:
    first = rd.buf[rd.pos]
    nbytes, kind, width = _EDGE_FORMATS[first & 0xF]
    v = int.from_bytes(rd.buf[rd.pos:rd.pos + nbytes], "little")
    rd.pos += nbytes
    nfields = {"H": 1, "V": 1, "L": 2, "Q": 4}[kind]
    vals = []
    for i in range(nfields):
        x = (v >> (4 + i * width)) & ((1 << width) - 1)
        if x & (1 << (width - 1)):
            x -= 1 << width
        vals.append(x)
    if kind == "H":
        return ("L", vals[0], 0)
    if kind == "V":
        return ("L", 0, vals[0])
    if kind == "L":
        return ("L", vals[0], vals[1])
    return ("Q", vals[0], vals[1], vals[2], vals[3])


def parse_compacted_font(data: bytes) -> Tuple[int, List[FontData]]:
    """DefineCompactedFont: UI16 fontId + uno o mas FontType."""
    (font_id,) = struct.unpack_from("<H", data, 0)
    fonts: List[FontData] = []
    rd = GfxReader(data, 2)
    while rd.pos < len(data):
        base = rd.pos                      # los offsets de glifo son relativos a aqui
        name = rd.cstr()
        flags = rd.u16()
        nominal = rd.u16()
        ascent = rd.s16()
        descent = rd.s16()
        leading = rd.s16()
        num_glyphs = rd.u32()
        glyph_bytes_len = rd.u32()
        rd.pos += glyph_bytes_len
        infos = []
        for _ in range(num_glyphs):
            code = rd.u16()
            adv = rd.s16()
            off = rd.u32()
            infos.append((code, adv, off))
        kern = []
        for _ in range(rd.ui30()):
            c1 = rd.u16()
            c2 = rd.u16()
            kern.append((c1, c2, rd.s16()))
        end_pos = rd.pos
        font = FontData(name, flags, nominal or 256, ascent, descent, leading, [], kern)
        for code, adv, off in infos:
            g = GfxReader(data, base + off)
            bbox = (g.si15(), g.si15(), g.si15(), g.si15())
            contours = []
            for _ in range(g.ui15()):
                mx = g.si15()
                my = g.si15()
                ref = g.ui30()
                back = None
                if ref & 1:                  # contorno compartido: salta a la referencia
                    back = g.pos
                    g.pos = base + (ref >> 1)
                    n_edges = g.ui30() >> 1
                else:
                    n_edges = ref >> 1
                edges = [_read_edge(g) for _ in range(n_edges)]
                if back is not None:
                    g.pos = back
                contours.append((mx, my, edges))
            font.glyphs.append(Glyph(code, adv, bbox, contours))
        fonts.append(font)
        rd.pos = end_pos
    return font_id, fonts


def _emit_straight(bw: BitWriter, dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return
    nb = sbits(dx, dy, 2) if (dx and dy) else sbits(dx or dy, 2)
    if nb > 17:                               # NumBits (UB4) + 2 = maximo 17 bits
        hx, hy = dx // 2, dy // 2
        _emit_straight(bw, hx, hy)
        _emit_straight(bw, dx - hx, dy - hy)
        return
    bw.ub(1, 1)       # TypeFlag = arista
    bw.ub(1, 1)       # StraightFlag
    bw.ub(4, nb - 2)
    if dx and dy:
        bw.ub(1, 1)   # GeneralLineFlag
        bw.sb(nb, dx)
        bw.sb(nb, dy)
    else:
        bw.ub(1, 0)
        if dx:
            bw.ub(1, 0)   # VertLineFlag = 0 -> horizontal
            bw.sb(nb, dx)
        else:
            bw.ub(1, 1)
            bw.sb(nb, dy)


def _emit_curve(bw: BitWriter, cx: int, cy: int, ax: int, ay: int) -> None:
    nb = sbits(cx, cy, ax, ay, 2)
    if nb > 17:
        # subdivide la cuadratica en t=0.5 con puntos absolutos redondeados
        p1x, p1y = cx, cy
        p2x, p2y = cx + ax, cy + ay
        m01 = (round(p1x / 2), round(p1y / 2))
        m12 = (round((p1x + p2x) / 2), round((p1y + p2y) / 2))
        mid = (round((m01[0] + m12[0]) / 2), round((m01[1] + m12[1]) / 2))
        _emit_curve(bw, m01[0], m01[1], mid[0] - m01[0], mid[1] - m01[1])
        _emit_curve(bw, m12[0] - mid[0], m12[1] - mid[1], p2x - m12[0], p2y - m12[1])
        return
    bw.ub(1, 1)
    bw.ub(1, 0)
    bw.ub(4, nb - 2)
    for v in (cx, cy, ax, ay):
        bw.sb(nb, v)


def encode_glyph_shape(glyph: Glyph, scale: int) -> Tuple[bytes, Tuple[int, int, int, int]]:
    """SHAPE de glifo (NumFillBits=1, NumLineBits=0; FillStyle0=1 como el IDE de Flash).
    Devuelve (bytes, bounds escalados xmin,xmax,ymin,ymax)."""
    bw = BitWriter()
    bw.ub(4, 1)
    bw.ub(4, 0)
    xs: List[int] = []
    ys: List[int] = []
    first = True
    for mx, my, edges in glyph.contours:
        x0, y0 = mx * scale, my * scale
        # StyleChangeRecord: moveTo (+ fill style en el primero)
        bw.ub(1, 0)            # TypeFlag
        bw.ub(1, 0)            # StateNewStyles
        bw.ub(1, 0)            # StateLineStyle
        bw.ub(1, 0)            # StateFillStyle1
        bw.ub(1, 1 if first else 0)  # StateFillStyle0
        bw.ub(1, 1)            # StateMoveTo
        mb = sbits(x0, y0)
        bw.ub(5, mb)
        bw.sb(mb, x0)
        bw.sb(mb, y0)
        if first:
            bw.ub(1, 1)        # FillStyle0 = 1
            first = False
        x, y = x0, y0
        xs.append(x)
        ys.append(y)
        for e in edges:
            if e[0] == "L":
                dx, dy = e[1] * scale, e[2] * scale
                _emit_straight(bw, dx, dy)
                x += dx
                y += dy
            else:
                cx, cy, ax, ay = (v * scale for v in e[1:])
                _emit_curve(bw, cx, cy, ax, ay)
                xs.append(x + cx)
                ys.append(y + cy)
                x += cx + ax
                y += cy + ay
            xs.append(x)
            ys.append(y)
        # cierra el contorno (GFx no guarda la arista de cierre)
        _emit_straight(bw, x0 - x, y0 - y)
    bw.ub(1, 0)
    bw.ub(5, 0)                 # EndShapeRecord
    if xs:
        bounds = (min(xs), max(xs), min(ys), max(ys))
    else:
        bounds = (0, 0, 0, 0)
    return bw.getvalue(), bounds


def _clamp16(v: int) -> Tuple[int, bool]:
    if v > 32767:
        return 32767, True
    if v < -32768:
        return -32768, True
    return v, False


def encode_define_font(font_id: int, font: FontData, name: Optional[str] = None,
                       prefer_font3: bool = True) -> Tag:
    """FontData -> DefineFont3 (em 20480) o, si algun valor de layout no cabe en SI16,
    DefineFont2 (em 1024).  Con nominal=256 DefineFont2 tambien es exacto (x4)."""
    name = font.name if name is None else name
    for use3 in ((True, False) if prefer_font3 else (False,)):
        em = 20480 if use3 else 1024
        scale_num = em / font.nominal
        scale = int(round(scale_num))
        if abs(scale - scale_num) > 1e-9:
            # nominal raro: escala no entera -> se redondea (imperceptible)
            pass
        overflow = False
        advances = []
        for g in font.glyphs:
            v, o = _clamp16(int(round(g.advance * scale_num)))
            advances.append(v)
            overflow |= o
        kern = []
        for c1, c2, adv in font.kerning:
            v, o = _clamp16(int(round(adv * scale_num)))
            kern.append((c1, c2, v))
            overflow |= o
        asc = max(0, int(round(font.ascent * scale_num)))
        desc = max(0, int(round(font.descent * scale_num)))
        lead, o = _clamp16(int(round(font.leading * scale_num)))
        overflow |= o or asc > 65535 or desc > 65535
        if overflow and use3 and prefer_font3:
            continue  # prueba DefineFont2
        break
    shapes = []
    bounds = []
    for g in font.glyphs:
        s, b = encode_glyph_shape(g, scale)
        shapes.append(s)
        bounds.append(b)
    n = len(font.glyphs)
    total = sum(len(s) for s in shapes)
    wide = (n * 2 + 2 + total) > 0xFFFF
    offsz = 4 if wide else 2
    offsets = []
    pos = (n + 1) * offsz
    for s in shapes:
        offsets.append(pos)
        pos += len(s)
    code_table_offset = pos
    name_b = name.encode("utf-8")[:255]
    flags = 0x80 | 0x04                     # HasLayout | WideCodes
    if wide:
        flags |= 0x08
    if font.italic:
        flags |= 0x02
    if font.bold:
        flags |= 0x01
    out = bytearray(struct.pack("<HBBB", font_id, flags, 1, len(name_b)))
    out += name_b
    out += struct.pack("<H", n)
    fmt = "<I" if wide else "<H"
    for o in offsets:
        out += struct.pack(fmt, o)
    out += struct.pack(fmt, code_table_offset)
    for s in shapes:
        out += s
    for g in font.glyphs:
        out += struct.pack("<H", g.code & 0xFFFF)
    out += struct.pack("<HHh", min(asc, 65535), min(desc, 65535), lead)
    for a in advances:
        out += struct.pack("<h", a)
    for b in bounds:
        out += encode_rect(b[0], b[1], b[2], b[3])
    out += struct.pack("<H", len(kern))
    for c1, c2, adv in kern:
        out += struct.pack("<HHh", c1, c2, adv)
    return Tag(T_DEFINEFONT3 if use3 else T_DEFINEFONT2, bytes(out))


@dataclass
class RawFont:
    """Fuente ya en formato SWF (DefineFont2/3, p.ej. de gfxfontlib.gfx).  Se copia tal
    cual cambiando solo id y nombre."""
    code: int
    data: bytes

    @property
    def name(self) -> str:
        n = self.data[4]
        return self.data[5:5 + n].rstrip(b"\0").decode("utf-8", "replace")

    @property
    def italic(self) -> bool:
        return bool(self.data[2] & 0x02)

    @property
    def bold(self) -> bool:
        return bool(self.data[2] & 0x01)

    @property
    def num_glyphs(self) -> int:
        n = self.data[4]
        return struct.unpack_from("<H", self.data, 5 + n)[0]

    @property
    def has_layout(self) -> bool:
        return bool(self.data[2] & 0x80)            # FontFlagsHasLayout

    def encode(self, font_id: int, name: Optional[str] = None) -> Tag:
        n = self.data[4]
        name_b = (self.name if name is None else name).encode("utf-8")[:255]
        out = struct.pack("<H", font_id) + self.data[2:4] + bytes([len(name_b)]) + name_b + self.data[5 + n:]
        return Tag(self.code, out)


def font_family(f) -> str:
    return f.name


def font_glyph_count(f) -> int:
    return len(f.glyphs) if isinstance(f, FontData) else f.num_glyphs


def encode_any_font(f, font_id: int, name: Optional[str] = None) -> Tag:
    if isinstance(f, FontData):
        return encode_define_font(font_id, f, name)
    return f.encode(font_id, name)


def font_has_layout(f) -> bool:
    return f.has_layout


def font_advance_em(f, code: int) -> Optional[float]:
    """Avance del caracter 'code' como fraccion del em (None si la fuente no lo trae o
    no tiene layout).  FontData (GFx) o RawFont (DefineFont2/3 ya en formato SWF)."""
    if isinstance(f, FontData):
        if not f.has_layout:
            return None
        for g in f.glyphs:
            if g.code == code:
                return g.advance / float(f.nominal)
        return None
    d = f.data
    flags = d[2]
    if not flags & 0x80:                       # sin FontFlagsHasLayout
        return None
    wide_off, wide_codes = flags & 0x08, flags & 0x04
    p = 5 + d[4]
    (n,) = struct.unpack_from("<H", d, p)
    p += 2
    table = p
    osz = 4 if wide_off else 2
    code_off = struct.unpack_from("<I" if wide_off else "<H", d, table + n * osz)[0]
    p = table + code_off
    csz = 2 if wide_codes else 1
    idx = None
    for i in range(n):
        c = struct.unpack_from("<H", d, p + 2 * i)[0] if wide_codes else d[p + i]
        if c == code:
            idx = i
            break
    if idx is None:
        return None
    p += n * csz + 6                           # codigos + ascent/descent/leading
    (adv,) = struct.unpack_from("<h", d, p + 2 * idx)
    return adv / (20480.0 if f.code == T_DEFINEFONT3 else 1024.0)


# ---------------------------------------------------------------------------
# Maquetacion de texto: diferencias GFx <-> Ruffle que se compensan en el SWF
# ---------------------------------------------------------------------------
_LETTERSPACING_RX = re.compile(rb'(?i)(letterspacing\s*=\s*["\'])\s*([-+]?\d*\.?\d*)\s*(["\'])')
_HTML_TOKEN_RX = re.compile(r"<(/?)([A-Za-z]+)([^>]*)>|([^<]+)")
_HTML_ATTR_RX = re.compile(r"""([A-Za-z]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def gfx_letter_spacing(value: float) -> int:
    """letterSpacing de <font letterSpacing="..."> tal como lo aplica GFx: sin la parte
    fraccionaria, hacia cero (0.5 -> 0, -0.6 -> 0, -1 -> -1).  Medido contra la wiki:
    classicvinewood (titular de 28 px: 248 px con 0, no 267 con 0.5),
    hammersteinfaust, universaluniform y appropriateassociates (-0.1), bedevinweston (-0.3)
    y kungfurainbowlazerforce (-0.4, TRADING CARDS en 7 lineas) parten como con 0; con floor
    (-1) o con los decimales no.  Descarta redondear al mas cercano con .5 hacia arriba
    (0.5 -> 1) y floor; solo -0.6 (himplants) distinguiria truncar de redondear a par, y no
    hay captura."""
    return int(value)


def truncate_html_letter_spacing(text: bytes) -> Tuple[bytes, int]:
    """Deja entero cada letterSpacing del HTML (ver gfx_letter_spacing).  Devuelve el texto
    nuevo y cuantos valores cambiaron."""
    changed = 0

    def fix(m):
        nonlocal changed
        try:
            v = float(m.group(2))
        except ValueError:
            return m.group(0)
        iv = gfx_letter_spacing(v)
        if iv == v:
            return m.group(0)
        changed += 1
        return m.group(1) + (b"%d.000000" % iv) + m.group(3)

    out = _LETTERSPACING_RX.sub(fix, text)
    return out, changed


_P_RX = re.compile(rb"(?is)(<p\b[^>]*>)(.*?)(</p>)")
_P_ALIGN_RX = re.compile(rb"(?i)align\s*=\s*[\"']?(\w+)")
_TRAILING_CLOSERS_RX = re.compile(rb"(?:</[^>]+>\s*)*$")
_ALIGN_NAMES = {0: b"left", 1: b"right", 2: b"center", 3: b"justify"}


def append_paragraph_spaces(text: bytes, html: bool, default_align: int) -> Tuple[bytes, int]:
    """Anade un espacio al final de cada parrafo alineado a la izquierda o justificado que
    no lo tenga (dentro del ultimo tramo de formato, para que mida lo mismo).  Ruffle mide
    la ultima palabra de un parrafo sin espacio y las demas con el; con el campo
    ensanchado un espacio, asi todas cumplen la regla del juego.  A la izquierda y en la
    ultima linea de un parrafo justificado un espacio final no se ve; centrado o a la
    derecha moveria la linea, asi que esos parrafos no se tocan."""
    n = 0
    if not html:
        if default_align not in (0, 3):
            return text, 0
        parts = re.split(rb"(\r\n|\r|\n)", text)
        for i in range(0, len(parts), 2):
            s = parts[i]
            if s.strip() and not s.endswith(b" "):
                parts[i] = s + b" "
                n += 1
        return b"".join(parts), n

    def fix(m):
        nonlocal n
        open_tag, inner, close = m.groups()
        am = _P_ALIGN_RX.search(open_tag)
        al = am.group(1).lower() if am else _ALIGN_NAMES.get(default_align, b"left")
        if al not in (b"left", b"justify"):
            return m.group(0)
        tm = _TRAILING_CLOSERS_RX.search(inner)
        body, closers = inner[:tm.start()], inner[tm.start():]
        if not body or body.endswith(b">") or body.endswith(b" ") or body.endswith(b"&#32;"):
            return m.group(0)
        if not re.sub(rb"<[^>]+>", b"", body).strip():
            return m.group(0)
        n += 1
        return open_tag + body + b" " + closers + close

    return _P_RX.sub(fix, text), n


def html_paragraphs(html_text: str) -> List[List[Tuple[Dict[str, str], str]]]:
    """Parrafos del HTML de un campo: [[(formato, texto), ...], ...].  El formato lleva
    face/size/letterspacing/align y 'b'/'i' si el tramo esta en <b>/<i>."""
    paras: List[List[Tuple[Dict[str, str], str]]] = [[]]
    stack: List[Dict[str, str]] = [{}]
    for m in _HTML_TOKEN_RX.finditer(html_text):
        closing, tag, attrs, text = m.group(1), (m.group(2) or "").lower(), m.group(3), m.group(4)
        if text is not None:
            paras[-1].append((stack[-1], _html.unescape(text)))
            continue
        if tag == "br" or (tag == "p" and not closing and paras[-1]):
            paras.append([])
        if tag == "p" and closing:
            paras.append([])
        if tag not in ("font", "p", "textformat", "b", "i"):
            continue
        if closing:
            if len(stack) > 1:
                stack.pop()
            continue
        cur = dict(stack[-1])
        if tag in ("b", "i"):
            cur[tag] = "1"
        for am in _HTML_ATTR_RX.finditer(attrs or ""):
            name = am.group(1).lower()
            val = am.group(2) if am.group(2) is not None else am.group(3)
            if tag == "font" and name in ("face", "size", "letterspacing", "kerning"):
                cur[name] = val
            elif tag == "p" and name == "align":
                cur["align"] = val.lower()
        stack.append(cur)
    return [p for p in paras if "".join(t for _, t in p).strip()]


class TextMetrics:
    """Anchos de texto de una fuente GFx (FontData) a un tamano, como los calcula el juego
    y como los calcula Ruffle, en twips.
    - GFx: avance (+ kerning) de cada glifo redondeado al twip; letterSpacing solo entre
      glifos; el espacio final de la linea no cuenta.
    - Ruffle (Font::evaluate / wrap_line): avance (+ kerning con el siguiente caracter del
      trozo medido) truncado al twip, mas letterSpacing en cada glifo; para decidir si una
      palabra cabe mide "palabra + espacio".
    Ajustado contra 19 parrafos cuya particion en lineas se ve en capturas del juego: solo
    "redondeo + letterSpacing entre glifos" los cumple todos."""

    def __init__(self, font: "FontData", size_tw: int, ls_tw: int, kerning: bool):
        self.adv = {g.code: g.advance for g in font.glyphs}
        self.kern = {(a, b): v for a, b, v in font.kerning} if kerning else {}
        self.k = size_tw / float(font.nominal)
        self.ls = ls_tw

    def _glyphs(self, text: str):
        for i, c in enumerate(text):
            a = self.adv.get(ord(c))
            if a is None:
                continue
            if i + 1 < len(text):
                a += self.kern.get((ord(c), ord(text[i + 1])), 0)
            yield a * self.k

    def gfx(self, text: str) -> int:
        n = 0
        tot = 0
        for tw in self._glyphs(text.rstrip(" ")):
            tot += int(math.floor(tw + 0.5)) + self.ls
            n += 1
        return tot - self.ls if n else 0

    def ruffle(self, text: str) -> int:
        return sum(int(tw) + self.ls for tw in self._glyphs(text))


def gfx_wrap(words: List[str], m: TextMetrics, width_tw: int) -> Optional[List[List[str]]]:
    """Lineas del juego (palabras separadas por un espacio).  None si una palabra sola no
    cabe (GFx la partiria por letras: no se modela)."""
    lines: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        if cur and m.gfx(" ".join(cur + [w])) > width_tw:
            if m.gfx(" ".join(cur)) > width_tw:
                return None
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur and m.gfx(" ".join(cur)) > width_tw and len(cur) == 1:
        return None
    lines.append(cur)
    return lines


def ruffle_width_interval(paras: List[str], m: TextMetrics, width_tw: int) -> Tuple[int, int]:
    """[lo, hi) de anchos de maquetacion con los que Ruffle parte cada parrafo como el
    juego (hi = 1<<30 si no hay limite; lo >= hi si no existe)."""
    lo, hi = 0, 1 << 30
    for text in paras:
        words = text.split(" ")
        lines = gfx_wrap(words, m, width_tw)
        if lines is None:
            return 1, 0
        pos = 0
        for k, line in enumerate(lines):
            pos += len(line)
            more = pos < len(words)
            pieces = [w + " " for w in line[:-1]]
            pieces.append(line[-1] + (" " if more else ""))
            c = sum(m.ruffle(p) for p in pieces)
            lo = max(lo, c)
            if k + 1 < len(lines):
                nxt = words[pos] + (" " if pos + 1 < len(words) else "")
                hi = min(hi, c + m.ruffle(nxt))
    return lo, hi


def html_dominant_run(html_text: str) -> Optional[Dict[str, str]]:
    """Formato (face, size, letterspacing, align) del tramo con mas caracteres de un HTML
    de campo de texto (<p align><font face size letterSpacing>...).  None si no hay texto."""
    stack: List[Dict[str, str]] = [{}]
    count: Dict[Tuple, int] = {}
    fmt_of: Dict[Tuple, Dict[str, str]] = {}
    for m in _HTML_TOKEN_RX.finditer(html_text):
        closing, tag, attrs, text = m.group(1), (m.group(2) or "").lower(), m.group(3), m.group(4)
        if text is not None:
            n = len(_html.unescape(text).strip("\r\n"))
            if n:
                cur = stack[-1]
                key = tuple(sorted(cur.items()))
                count[key] = count.get(key, 0) + n
                fmt_of[key] = cur
            continue
        if tag not in ("font", "p", "textformat"):
            continue
        if closing:
            if len(stack) > 1:
                stack.pop()
            continue
        cur = dict(stack[-1])
        for am in _HTML_ATTR_RX.finditer(attrs or ""):
            name = am.group(1).lower()
            val = am.group(2) if am.group(2) is not None else am.group(3)
            if tag == "font" and name in ("face", "size", "letterspacing", "kerning"):
                cur[name] = val
            elif tag == "p" and name == "align":
                cur["align"] = val.lower()
        stack.append(cur)
    if not count:
        return None
    return fmt_of[max(count, key=lambda k: count[k])]


# Frecuencia de los caracteres en los textos de las webs (strings_web.json sin codigos ~x~ ni
# etiquetas; los que pasan del 0.05%).  Sirve para estimar, sin conocer el texto, cuantos
# glifos caben en una linea y cuantos redondean hacia arriba (robust_wrap_extra).
_CHAR_FREQ = {
    " ": 0.1526, "e": 0.0946, "a": 0.0641, "t": 0.0622, "o": 0.0612, "n": 0.0525, "i": 0.0516,
    "r": 0.0508, "s": 0.0464, "l": 0.0354, "h": 0.0338, "c": 0.0254, "u": 0.0246, "d": 0.0235,
    "g": 0.016, "y": 0.0159, "m": 0.0149, "p": 0.0149, "w": 0.0127, "f": 0.0126, ".": 0.0103,
    "b": 0.0099, "k": 0.009, "v": 0.0087, "S": 0.008, "T": 0.0054, "B": 0.0051, "C": 0.0048,
    "A": 0.0048, "P": 0.0038, ",": 0.0038, "I": 0.0035, "'": 0.0035, "L": 0.0031, "G": 0.0031,
    "M": 0.003, "E": 0.003, "Y": 0.0029, "O": 0.0029, "-": 0.0028, "W": 0.0028, "R": 0.0028,
    "F": 0.0026, "H": 0.0023, "D": 0.0022, "N": 0.0021, "x": 0.0016, "V": 0.0014, "J": 0.0012,
    "@": 0.0012, "z": 0.0011, "j": 0.0009, "U": 0.0009, '"': 0.0008, "!": 0.0008, "K": 0.0008,
    "0": 0.0007, "1": 0.0007, "q": 0.0007, "?": 0.0007, "2": 0.0005,
}


def robust_wrap_extra(font: "FontData", size_tw: int, ls_tw: int, width_tw: int) -> Optional[int]:
    """Ensanchado (twips) con el que Ruffle acierta mas a menudo las lineas del juego para un
    texto que no se conoce, con este formato y este ancho.

    En cada decision de salto (linea L + palabra w) el juego parte si G(L w) > W (avances
    redondeados al twip, sin el espacio final, letterSpacing entre glifos) y Ruffle si
    R(L w + " ") > W + e (avances truncados, con el espacio final, letterSpacing tras cada
    glifo).  R = G - d + espacio + 2 ls, donde d es cuantos glifos de la linea tienen un
    avance con fraccion >= 0.5 (GFx sube, Ruffle baja).  Las decisiones que se pueden errar son
    las de lineas casi llenas; aciertan con e = espacio + 2 ls - d, y como d no se conoce se
    toma la esperada en una linea llena: n = W / avance medio glifos, cada caracter con su
    frecuencia (_CHAR_FREQ) y sus avances reales a este tamano.  La ronda 4 suponia medio twip
    por glifo; con Chalet a 13 px solo redondea hacia arriba el 7 % de los glifos (hushsmush
    HUS_SITE_DESC quedaba 0.4 px corto).  Sobre los 666 campos estaticos con saltos cuyo
    ancho exacto se conoce, e cae dentro en 647 (el medio twip, en 617)."""
    adv = {g.code: g.advance for g in font.glyphs}
    if 32 not in adv or not size_tw:
        return None
    k = size_tw / float(font.nominal)
    wsum = dsum = fsum = 0.0
    for ch, f in _CHAR_FREQ.items():
        a = adv.get(ord(ch))
        if a is None:
            continue
        tw = a * k
        wsum += f * (math.floor(tw + 0.5) + ls_tw)
        dsum += f * (math.floor(tw + 0.5) - int(tw))
        fsum += f
    if fsum <= 0 or wsum <= 0:
        return None
    n = width_tw / (wsum / fsum)
    return int(adv[32] * k) + 2 * ls_tw - int(round(n * dsum / fsum))


def pick_wrap_width(ivals: List[Tuple[int, int]], target: int) -> Tuple[int, bool]:
    """Ancho de maquetacion dentro de todos los intervalos [lo, hi) (el mas cercano a
    'target'); si no tienen punto comun, el que cumple mas intervalos (a igualdad, el mas
    cercano a 'target').  Devuelve (ancho, cumple todos)."""
    lo = max(a for a, _ in ivals)
    hi = min(b for _, b in ivals)
    if lo < hi:
        return min(max(target, lo), hi - 1), True
    cands = {target} | {a for a, _ in ivals} | {b - 1 for _, b in ivals}
    best = max(sorted(cands), key=lambda x: (sum(1 for a, b in ivals if a <= x < b), -abs(x - target)))
    return best, False


# ---------------------------------------------------------------------------
# Textos que el script pone en los campos (labels GXT): se conocen al convertir
# ---------------------------------------------------------------------------
DEFAULT_STRINGS = [os.path.join(WORK_V, "text", n) for n in ("strings_web.json", "strings_global.json")]
_STRINGS_CACHE: Dict[Tuple[str, ...], "GameStrings"] = {}


def joaat(text: str) -> int:
    h = 0
    for ch in text.lower().encode("utf-8"):
        h = (h + ch) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    return (h + (h << 15)) & 0xFFFFFFFF


class GameStrings:
    """Textos del juego como los busca el host (host.js lookup): por label y, si no esta,
    por el JOAAT del label en minusculas (claves hex de strings_global.json)."""

    def __init__(self, paths: List[str]):
        import json
        self.table: Dict[str, str] = {}
        for p in paths:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as fh:
                    for k, v in json.load(fh).items():
                        if isinstance(v, str):
                            self.table.setdefault(k, v)

    def lookup(self, label: str) -> Optional[str]:
        if not label:
            return None
        v = self.table.get(label)
        if v is None:
            hx = "%08x" % joaat(label)
            v = self.table.get(hx) or self.table.get(hx.upper())
        return v


def load_game_strings(paths: Optional[List[str]]) -> Optional[GameStrings]:
    key = tuple(paths or DEFAULT_STRINGS)
    if key not in _STRINGS_CACHE:
        _STRINGS_CACHE[key] = GameStrings(list(key))
    st = _STRINGS_CACHE[key]
    return st if st.table else None


def gxt_paragraphs(s: str) -> List[Optional[str]]:
    """Parrafos del texto que el host escribe en un campo para un label GXT (formatGxt de
    host.js): ~n~ y <br> parten parrafos; <C>, colores y huecos (~r~, ~a~, ~1~...) no ocupan.
    None en los parrafos cuyo ancho no se puede medir con el formato del campo (negrita o
    cursiva ~h~, o HTML propio como <li> o <font>)."""
    s = re.sub(r"</?C>", "", s)
    out: List[Optional[str]] = []
    for p in re.split(r"(?i)~n~|<br\s*/?>", s):
        if re.search(r"(?i)~(h|bold|italic)~", p) or "<" in p:
            out.append(None)
            continue
        p = re.sub(r"~[A-Za-z0-9_]+~", "", p)
        out.append(_html.unescape(p) if "&" in p else p)
    return out


# ---------------------------------------------------------------------------
# ActionScript (bytecode AS2): geometria que lee y labels que escribe, por nombre de instancia
# ---------------------------------------------------------------------------
_AS_GEO_PROPS = {"_width", "_x", "getBounds", "getRect", "_xscale", "_height", "_yscale", "_y"}
_AS_PROP_INDEX = {0: "_x", 1: "_y", 2: "_xscale", 3: "_yscale", 8: "_width", 9: "_height"}
_AS_GI_CHAIN = {"com", "rockstargames", "ui", "game", "GameInterface", "GENERIC_TYPE", "this"}


def _as_actions(code: bytes):
    pos, end = 0, len(code)
    while pos < end:
        op = code[pos]
        pos += 1
        if op >= 0x80 and pos + 2 <= end:
            (ln,) = struct.unpack_from("<H", code, pos)
            pos += 2
            yield op, code[pos:pos + ln]
            pos += ln
        else:
            yield op, b""


def _as_push_values(payload: bytes, pool: List[str]) -> list:
    vals = []
    p = 0
    try:
        while p < len(payload):
            t = payload[p]
            p += 1
            if t == 0:
                e = payload.index(b"\0", p)
                vals.append(("s", payload[p:e].decode("latin1")))
                p = e + 1
            elif t in (1, 7):
                vals.append(("n", struct.unpack_from("<f" if t == 1 else "<i", payload, p)[0]))
                p += 4
            elif t in (2, 3):
                vals.append(("u", None))
            elif t in (4, 5):
                vals.append(("r" if t == 4 else "b", payload[p]))
                p += 1
            elif t == 6:
                hi, lo = struct.unpack_from("<II", payload, p)
                vals.append(("n", struct.unpack("<d", struct.pack("<II", lo, hi))[0]))
                p += 8
            elif t in (8, 9):
                i = payload[p] if t == 8 else struct.unpack_from("<H", payload, p)[0]
                vals.append(("s", pool[i] if i < len(pool) else None))
                p += 1 if t == 8 else 2
            else:
                break
    except (IndexError, ValueError, struct.error):
        pass
    return vals


def _as_scan_block(code: bytes, geo: Dict[str, set], texts: Dict[str, set]) -> None:
    """Recorre un bloque de acciones AS2 en orden (las funciones van en linea) y apunta:
    - geo[nombre]: propiedades geometricas que se leen o escriben de 'x.nombre' o 'nombre'
      (GetMember/GetVariable seguido de Push "_width"...; getProperty(ruta, indice);
      registros cargados con un GetMember o con un parametro de DefineFunction2).
    - texts[nombre]: labels literales que el script escribe en 'x.nombre' con
      GameInterface.call("SET_TEXT_WITH_TRANSLATION", GENERIC_TYPE, "LABEL", x.nombre, ...) o
      setLocalisedText(x.nombre, "LABEL").
    Comprobado contra el AS decompilado por JPEXS de las 96 peliculas: mismos accesos y
    pares, salvo los que el decompilado no ve (los de las
    versiones 2013, cuyo decompilado no existe) y concatenaciones ("FLAG_" + i)."""
    pool: List[str] = []
    regs: Dict[int, str] = {}
    obj: Optional[str] = None
    last_push = None
    ev: list = []            # ('s', cadena) | ('o', nombre obtenido) | ('x', otro valor) | ('a', op)
    for op, pl in _as_actions(code):
        cur_obj = None
        if op == 0x88:                                   # ConstantPool
            pool = []
            try:
                (n,) = struct.unpack_from("<H", pl)
                p = 2
                for _ in range(n):
                    e = pl.index(b"\0", p)
                    pool.append(pl[p:e].decode("latin1"))
                    p = e + 1
            except (ValueError, struct.error):
                pass
            last_push = None
            continue
        if op == 0x96:                                   # Push
            vals = _as_push_values(pl, pool)
            if vals and obj is not None and vals[0][0] == "s" and vals[0][1] in _AS_GEO_PROPS:
                geo.setdefault(obj, set()).add(vals[0][1])
            for i in range(len(vals) - 1):
                a, b_ = vals[i], vals[i + 1]
                if a[0] == "r" and b_[0] == "s" and b_[1] in _AS_GEO_PROPS and regs.get(a[1]):
                    geo.setdefault(regs[a[1]], set()).add(b_[1])
            for t, v in vals:
                if t == "s" and v is not None:
                    if v == "SET_TEXT_WITH_TRANSLATION":
                        i = len(ev) - 1
                        while i >= 0 and ev[i][1] in _AS_GI_CHAIN:
                            i -= 1
                        if i >= 1 and ev[i][0] == "s" and ev[i - 1][0] == "o" and ev[i - 1][1]:
                            texts.setdefault(ev[i - 1][1], set()).add(ev[i][1])
                    elif v == "setLocalisedText":
                        i = len(ev) - 1
                        while i >= 0 and (ev[i][0] == "x" or ev[i][1] == "this"):
                            i -= 1
                        if i >= 0 and ev[i][0] == "o" and ev[i][1]:
                            target = ev[i][1]
                            for _ in range(12):
                                if i >= 1 and ev[i][0] == "o" and ev[i - 1] == ("s", ev[i][1]):
                                    i -= 2
                                elif i >= 0 and (ev[i][0] == "x" or ev[i][1] == "this"):
                                    i -= 1
                                else:
                                    break
                            if i >= 0 and ev[i][0] == "s" and not (i + 1 < len(ev) and ev[i + 1] == ("o", ev[i][1])):
                                texts.setdefault(target, set()).add(ev[i][1])
                    ev.append(("s", v))
                else:
                    ev.append(("x", v))
            last_push = vals
        elif op in (0x4E, 0x1C):                         # GetMember / GetVariable
            name = None
            if last_push and last_push[-1][0] == "s" and last_push[-1][1]:
                name = re.split(r"[./:]", last_push[-1][1])[-1]
            cur_obj = name
            ev.append(("o", name))
            last_push = None
        elif op == 0x22:                                 # GetProperty(ruta, indice)
            if last_push and len(last_push) >= 2 and last_push[-2][0] == "s" and last_push[-1][0] == "n":
                prop = _AS_PROP_INDEX.get(int(last_push[-1][1]))
                if prop and last_push[-2][1]:
                    geo.setdefault(re.split(r"[./:]", last_push[-2][1])[-1], set()).add(prop)
            ev.append(("a", op))
            last_push = None
        elif op == 0x87 and pl:                          # StoreRegister (deja el valor en la pila)
            if obj is not None:
                regs[pl[0]] = obj
            else:
                regs.pop(pl[0], None)
            cur_obj = obj
            last_push = None
        elif op == 0x8E:                                 # DefineFunction2: parametros en registros
            try:
                p = pl.index(b"\0") + 1
                (npar,) = struct.unpack_from("<H", pl, p)
                p += 5
                for _ in range(npar):
                    r = pl[p]
                    e = pl.index(b"\0", p + 1)
                    if r:
                        regs[r] = pl[p + 1:e].decode("latin1")
                    p = e + 1
            except (ValueError, IndexError, struct.error):
                pass
            ev.append(("a", op))
            last_push = None
        elif op == 0x4C:                                 # PushDuplicate
            cur_obj = obj
            last_push = None
        else:
            ev.append(("a", op))
            last_push = None
        obj = cur_obj
        if len(ev) > 64:
            del ev[:32]


def scan_actionscript(tags: List[Tag]) -> Tuple[Dict[str, set], Dict[str, set]]:
    """(geometria leida/escrita por nombre de instancia, labels escritos por nombre) de todo el
    AS2 de la pelicula (DoAction y DoInitAction, tambien dentro de clips)."""
    geo: Dict[str, set] = {}
    texts: Dict[str, set] = {}
    for t in tags:
        if t.code == T_DOACTION:
            _as_scan_block(t.data, geo, texts)
        elif t.code == T_DOINITACTION and len(t.data) > 2:
            _as_scan_block(t.data[2:], geo, texts)
        elif t.code == T_DEFINESPRITE:
            g2, t2 = scan_actionscript(split_sprite(t.data)[2])
            for k, v in g2.items():
                geo.setdefault(k, set()).update(v)
            for k, v in t2.items():
                texts.setdefault(k, set()).update(v)
    return geo, texts


# ---------------------------------------------------------------------------
# Cajas de los clips (fotograma 1) y nombres de instancia: holgura de un campo dentro de los
# clips cuya caja lee el script
# ---------------------------------------------------------------------------
_BOUNDS_TAGS = {2, 22, 32, 83, 11, 33, 46, 84, T_DEFINEEDITTEXT}


class _Bits:
    def __init__(self, data: bytes, pos: int):
        self.b, self.bit = data, pos * 8

    def ub(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.bit >> 3] >> (7 - (self.bit & 7))) & 1)
            self.bit += 1
        return v

    def sb(self, n: int) -> int:
        v = self.ub(n)
        return v - (1 << n) if n and v >> (n - 1) else v

    def byte_pos(self) -> int:
        return (self.bit + 7) >> 3


def parse_place_object(t: Tag):
    """(profundidad, id | None, matriz (a, b, c, d, tx, ty) | None, nombre | None, mueve) de
    un PlaceObject2/3."""
    d = t.data
    if t.code == 26:
        f, f2, p = d[0], 0, 1
    else:
        f, f2, p = d[0], d[1], 2
    (depth,) = struct.unpack_from("<H", d, p)
    p += 2
    if t.code == 70 and (f2 & 0x08) and (f2 & 0x04):
        p = d.index(b"\0", p) + 1
    cid = None
    if f & 0x02:
        (cid,) = struct.unpack_from("<H", d, p)
        p += 2
    mat = None
    if f & 0x04:
        r = _Bits(d, p)
        a = dd = 1.0
        b_ = c_ = 0.0
        if r.ub(1):
            n = r.ub(5)
            a, dd = r.sb(n) / 65536.0, r.sb(n) / 65536.0
        if r.ub(1):
            n = r.ub(5)
            b_, c_ = r.sb(n) / 65536.0, r.sb(n) / 65536.0
        n = r.ub(5)
        tx, ty = r.sb(n), r.sb(n)
        mat = (a, b_, c_, dd, tx, ty)
        p = r.byte_pos()
    if f & 0x08:                                          # CXFORMWITHALPHA
        r = _Bits(d, p)
        add, mult, n = r.ub(1), r.ub(1), r.ub(4)
        r.ub(4 * n * (add + mult))
        p = r.byte_pos()
    if f & 0x10:
        p += 2
    name = None
    if f & 0x20:
        e = d.index(b"\0", p)
        name = d[p:e].decode("latin1")
    return depth, cid, mat, name, bool(f & 0x01)


def _mat_mul(p, q):
    return (p[0] * q[0] + p[2] * q[1], p[1] * q[0] + p[3] * q[1],
            p[0] * q[2] + p[2] * q[3], p[1] * q[2] + p[3] * q[3],
            p[0] * q[4] + p[2] * q[5] + p[4], p[1] * q[4] + p[3] * q[5] + p[5])


def _xform_rect(m, r):
    xs = [m[0] * x + m[2] * y + m[4] for x in (r[0], r[1]) for y in (r[2], r[3])]
    ys = [m[1] * x + m[3] * y + m[5] for x in (r[0], r[1]) for y in (r[2], r[3])]
    return (min(xs), max(xs), min(ys), max(ys))


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0, 0)


class MovieLayout:
    """Nombres de instancia de cada caracter y cajas de los clips en su fotograma 1 (como las
    ve _width / getBounds al entrar en la pagina)."""

    def __init__(self, tags: List[Tag]):
        self.rects: Dict[int, Tuple[int, int, int, int]] = {}
        self.edit_ids: set = set()
        self.sprites: Dict[int, list] = {}
        self.names: Dict[int, set] = {}
        self._walk(tags)
        self._memo: Dict[int, Optional[tuple]] = {}

    def _walk(self, tags: List[Tag]) -> None:
        for t in tags:
            if t.code in _BOUNDS_TAGS and len(t.data) > 3:
                (cid,) = struct.unpack_from("<H", t.data)
                try:
                    self.rects[cid] = decode_rect(t.data, 2)
                except (IndexError, struct.error):
                    continue
                if t.code == T_DEFINEEDITTEXT:
                    self.edit_ids.add(cid)
            elif t.code == T_DEFINESPRITE:
                sid, _, sub = split_sprite(t.data)
                self._walk(sub)
                dl: Dict[int, list] = {}
                first = True
                for st in sub:
                    if st.code == T_SHOWFRAME:
                        first = False
                    if st.code not in (26, 70):
                        if first and st.code in (5, 28):
                            dl.pop(struct.unpack_from("<H", st.data, 2 if st.code == 5 else 0)[0], None)
                        continue
                    try:
                        depth, cid, mat, name, move = parse_place_object(st)
                    except (IndexError, ValueError, struct.error):
                        continue
                    if cid is not None and name:
                        self.names.setdefault(cid, set()).add(name)
                    if not first:
                        continue
                    cur = dl.get(depth, [None, None, None])
                    if cid is not None:
                        cur = [cid, cur[1] if move else None, None]
                    if mat is not None:
                        cur[1] = mat
                    if name is not None:
                        cur[2] = name
                    dl[depth] = cur
                self.sprites[sid] = [(dp, v[0], v[1] or _IDENTITY, v[2]) for dp, v in sorted(dl.items())
                                     if v[0] is not None]
            elif t.code in (26, 70):
                try:
                    depth, cid, mat, name, move = parse_place_object(t)
                except (IndexError, ValueError, struct.error):
                    continue
                if cid is not None and name:
                    self.names.setdefault(cid, set()).add(name)

    def bounds(self, cid: int, depth: int = 0) -> Optional[tuple]:
        if cid in self._memo:
            return self._memo[cid]
        if cid in self.sprites and depth < 40:
            r = None
            for _, ch, mat, _ in self.sprites[cid]:
                cb = self.bounds(ch, depth + 1)
                if cb is None:
                    continue
                cb = _xform_rect(mat, cb)
                r = cb if r is None else (min(r[0], cb[0]), max(r[1], cb[1]), min(r[2], cb[2]), max(r[3], cb[3]))
        else:
            r = self.rects.get(cid)
        self._memo[cid] = r
        return r

    def field_slack(self, clip_ids: set) -> Dict[int, Tuple[float, float]]:
        """{id de campo: (holgura izquierda, holgura derecha)} en twips del campo: cuanto puede
        crecer hacia cada lado sin agrandar la caja de ninguno de los clips 'clip_ids' que lo
        contienen (en su fotograma 1).  Con giro o sesgo, 0."""
        out: Dict[int, Tuple[float, float]] = {}
        for sid in clip_ids:
            box = self.bounds(sid)
            if box is None:
                continue
            stack = [(sid, _IDENTITY, 0)]
            while stack:
                cur, m, dep = stack.pop()
                for _, ch, mat, _ in self.sprites.get(cur, ()):
                    mm = _mat_mul(m, mat)
                    if ch in self.sprites and dep < 40:
                        stack.append((ch, mm, dep + 1))
                    elif ch in self.edit_ids:
                        r = self.rects[ch]
                        if abs(mm[1]) < 1e-9 and abs(mm[2]) < 1e-9 and mm[0] > 0:
                            x0, x1 = mm[0] * r[0] + mm[4], mm[0] * r[1] + mm[4]
                            sl = (max(0.0, (x0 - box[0]) / mm[0]), max(0.0, (box[1] - x1) / mm[0]))
                        else:
                            # girado o volteado: lo que puede crecer cada lado sin salir de la caja
                            def inside(d_left, d_right, r=r, mm=mm, box=box):
                                q = _xform_rect(mm, (r[0] - d_left, r[1] + d_right, r[2], r[3]))
                                return (q[0] >= box[0] - 0.5 and q[1] <= box[1] + 0.5
                                        and q[2] >= box[2] - 0.5 and q[3] <= box[3] + 0.5)
                            sl = []
                            for side in (0, 1):
                                lo_d, hi_d = 0.0, 2000.0
                                if not inside(0, 0):
                                    sl.append(0.0)
                                    continue
                                for _ in range(24):
                                    mid = (lo_d + hi_d) / 2
                                    if inside(mid if side == 0 else 0, mid if side == 1 else 0):
                                        lo_d = mid
                                    else:
                                        hi_d = mid
                                sl.append(lo_d)
                            sl = (sl[0], sl[1])
                        old = out.get(ch)
                        out[ch] = sl if old is None else (min(old[0], sl[0]), min(old[1], sl[1]))
        return out


NBSP_MISSING_EM = 0.5      # avance con que GFx pinta un U+00A0 que la fuente no trae


def ensure_nbsp_glyph(font: "FontData") -> bool:
    """Anade U+00A0 (espacio duro), vacio y de medio em, a una fuente que no lo trae (127 de
    las 131 fuentes GFx de las webs y todas las de las font libs).  Sin glifo, Ruffle lo pinta
    con ancho 0 y el texto se junta.  GFx lo pinta en blanco y mas ancho que un espacio;
    medido en capturas del juego (hueco de ". &nbsp;" menos un hueco normal) en tres webs
    (hammersteinfaust, appropriateassociates, lossantosfreegans): entre 5.7 y 7.3 px a 12-15
    px, medio em.  Y los cortes de linea de las capturas lo piden: un parrafo de grainoftruth
    solo parte igual con el nbsp >= 0.43 em; otros de appropriateassociates y grainoftruth
    salen con cualquier valor entre un espacio y ~0.75 em, y no con 0.  No es punto de corte
    ni en GFx ni en Ruffle (Font::wrap_line solo corta en U+0020).  Se anade al final para no
    mover los indices de glifo que usa DefineText."""
    if not font.has_layout or not font.glyphs:
        return False
    codes = {g.code for g in font.glyphs}
    if 0xA0 in codes or 0x20 not in codes:
        return False
    adv = int(round(font.nominal * NBSP_MISSING_EM))
    font.glyphs.append(Glyph(0xA0, adv, (0, 0, -1, -1), []))
    return True


# Metricas tipicas (fraccion del em) para una fuente sin layout y sin copia en las font
# libs: ascent/descent de Arial (0.905/0.212), espacio de Helvetica/Arial (0.278 em).
_TYPICAL_ASCENT = 0.905
_TYPICAL_DESCENT = 0.212
_BLANK_ADVANCE = {0x2002: 0.5, 0x2003: 1.0, 0x2009: 0.2, 0x200A: 0.1, 0x3000: 1.0}
_SPACE_ADVANCE = 0.278


def _glyph_is_blank(g: Glyph) -> bool:
    return not g.contours or g.bbox[2] < g.bbox[0]


def _advance_from_bbox(g: Glyph, nominal: int, space_adv: float) -> int:
    """Avance estimado de un glifo con solo su caja: xmax + xmin, es decir, el mismo
    margen a la derecha que a la izquierda.  Medido contra los 15.5k glifos con layout de
    las font libs: exacto o +-1 (de 256) en el 50%, +-5 (2% del em) en el 72%."""
    if _glyph_is_blank(g):
        return int(round(nominal * (_BLANK_ADVANCE.get(g.code) or space_adv)))
    xmin, xmax = g.bbox[0], g.bbox[2]
    return max(1, xmax + xmin, (xmax - xmin + 1) // 2)


def synthesize_layout(font: FontData, donor: Optional[FontData]) -> str:
    """Rellena el layout de una fuente GFx que no lo trae (sin FF_HasLayout: ascent,
    descent, leading y todos los avances a 0).  Emitida asi, un campo de texto con
    useOutlines la maquetaria con ancho 0 (invisible en Ruffle).  El juego no la usa para
    esos campos: busca la familia por nombre en las font libs y maqueta con esa copia.
    Imitamos eso con 'donor' (la copia de la misma familia en font_lib_web/efigs...):
    ascent/descent/leading, avance de cada glifo por codigo y kerning.  Los glifos que la
    copia no tiene (o todos, si no hay copia) se estiman con su caja; sin copia, ascent y
    descent salen de las cajas o de metricas tipicas.  Devuelve un resumen para el log."""
    n = font.nominal
    k = n / donor.nominal if donor else 1.0
    dadv: Dict[int, float] = {g.code: g.advance * k for g in donor.glyphs} if donor else {}
    space_adv = dadv[0x20] / n if 0x20 in dadv else _SPACE_ADVANCE
    guessed = 0
    for g in font.glyphs:
        if g.code in dadv:
            g.advance = int(round(dadv[g.code]))
        else:
            g.advance = _advance_from_bbox(g, n, space_adv)
            guessed += 1
    inked = [g for g in font.glyphs if not _glyph_is_blank(g)]
    top = max((-g.bbox[1] for g in inked), default=0)
    bottom = max((g.bbox[3] for g in inked), default=0)
    if donor:
        font.ascent = int(round(donor.ascent * k))
        font.descent = int(round(donor.descent * k))
        font.leading = int(round(donor.leading * k))
        if not font.kerning:
            codes = {g.code for g in font.glyphs}
            font.kerning = [(a, b, int(round(v * k))) for a, b, v in donor.kerning
                            if a in codes and b in codes]
        src = "%s%s%s" % (donor.name, " italic" if donor.italic else "", " bold" if donor.bold else "")
    else:
        font.ascent = max(top, int(round(n * _TYPICAL_ASCENT)))
        font.descent = max(bottom, int(round(n * _TYPICAL_DESCENT)))
        font.leading = 0
        src = "cajas de los glifos"
    font.flags |= GFX_FF_HASLAYOUT
    return "layout de %s (%d/%d avances estimados por caja, ascent %d descent %d leading %d)" % (
        src, guessed, len(font.glyphs), font.ascent, font.descent, font.leading)


# ===========================================================================
# Biblioteca de fuentes del juego (fontmap.xml + font_lib_*.gfx + gfxfontlib.gfx)
# ===========================================================================
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass
class LibFont:
    lib: str           # nombre del archivo de origen
    export: str        # nombre de exportacion ("$Font2")
    font: object       # FontData | RawFont
    order: int         # prioridad (menor = preferida)
    placeholder: bool  # viene de gfxfontlib.gfx (fuentes "de autor")


class FontLibrary:
    def __init__(self, extract_root: str = DEFAULT_EXTRACT,
                 lib_paths: Optional[List[str]] = None, fontmap_path: Optional[str] = None,
                 language: str = "efigs", nbsp_glyph: bool = True):
        self.extract_root = extract_root
        self.nbsp_glyph = nbsp_glyph        # U+00A0 en las fuentes GFx que no lo traen
        self.fonts: List[LibFont] = []
        self.fontmap: Dict[str, Tuple[str, bool]] = {}
        self.loaded_libs: List[str] = []
        if fontmap_path is None:
            for c in FONTMAP_CANDIDATES:
                p = os.path.join(extract_root, c)
                if os.path.isfile(p):
                    fontmap_path = p
                    break
        if fontmap_path and os.path.isfile(fontmap_path):
            self._load_fontmap(fontmap_path, language)
        if lib_paths is None:
            lib_paths = [os.path.join(extract_root, c) for c in FONT_LIB_CANDIDATES]
        seen = set()
        for order, p in enumerate(lib_paths):
            if not os.path.isfile(p):
                continue
            base = os.path.basename(p).lower()
            if base in seen:          # misma lib en base y update: solo la primera (update)
                continue
            seen.add(base)
            self._load_lib(p, order)
        self._cache: Dict[str, Optional[LibFont]] = {}

    def _load_fontmap(self, path: str, language: str) -> None:
        # fontmap.xml no es XML valido (comentarios "<! --- ... />"): se lee con regex.
        text = open(path, "r", encoding="utf-8", errors="replace").read()
        rx = re.compile(r"<\s*%s\s+name\s*=\s*\"([^\"]+)\"\s+mapping\s*=\s*\"([^\"]+)\"\s+bold\s*=\s*\"(\d)\"" % language)
        for m in rx.finditer(text):
            self.fontmap[m.group(1)] = (m.group(2), m.group(3) == "1")

    def _load_lib(self, path: str, order: int) -> None:
        try:
            movie = read_movie(open(path, "rb").read())
        except Exception as ex:  # pragma: no cover
            log("  warning: could not read font library %s: %s" % (path, ex))
            return
        placeholder = os.path.basename(path).lower().startswith("gfxfontlib")
        by_id: Dict[int, object] = {}
        exports: List[Tuple[int, str]] = []
        for t in movie.tags:
            if t.code == GFX_DEFINECOMPACTEDFONT:
                fid, fl = parse_compacted_font(t.data)
                if fl:
                    if self.nbsp_glyph:
                        ensure_nbsp_glyph(fl[0])
                    by_id[fid] = fl[0]
            elif t.code in (T_DEFINEFONT2, T_DEFINEFONT3):
                (fid,) = struct.unpack_from("<H", t.data, 0)
                by_id[fid] = RawFont(t.code, t.data)
            elif t.code == T_EXPORTASSETS:
                exports.extend(parse_export_assets(t.data))
        for cid, name in exports:
            if cid in by_id:
                self.fonts.append(LibFont(os.path.basename(path), name, by_id[cid], order, placeholder))
        self.loaded_libs.append(path)

    def resolve(self, name: str) -> Optional[LibFont]:
        """Resuelve un nombre como lo haria el juego: alias "$..." via fontmap hacia una
        familia; si no, busqueda directa por familia o por nombre exportado."""
        if name in self._cache:
            return self._cache[name]
        target_family = self.fontmap.get(name, (None, False))[0]
        best, best_score = None, -1
        for lf in self.fonts:
            if font_glyph_count(lf.font) == 0:
                continue
            fam = font_family(lf.font)
            score = 0
            want = _norm(target_family or name)
            have = _norm(fam)
            if have and have == want:
                score += 8                      # familia exacta
            elif have and want and len(min(have, want, key=len)) >= 6 and (
                    have.startswith(want) or want.startswith(have)):
                score += 6                      # variante ("...Sixty" / "...SixtyScale")
            if lf.export == name:
                score += 4
            if score == 0:
                continue
            if not lf.placeholder:
                score += 2
            score = score * 100 - lf.order
            if score > best_score:
                best, best_score = lf, score
        self._cache[name] = best
        return best

    def layout_donor(self, font: FontData) -> Optional[FontData]:
        """Copia con layout de una fuente GFx que no lo trae, como la encontraria el juego
        por nombre: misma familia (o variante "...Scale"), mismo estilo si lo hay y, entre
        iguales, la primera en el orden de las libs (el de resolve()).  Sin nombre, o sin
        familia en las libs, vale la fuente cuyos contornos coincidan en mas de la mitad
        de los glifos (la que mas coincida)."""
        want = _norm(font.name)
        mine = {g.code: g.contours for g in font.glyphs if g.contours}
        best, best_key = None, None
        for lf in self.fonts:
            f = lf.font
            if not isinstance(f, FontData) or not f.glyphs or not f.has_layout:
                continue
            have = _norm(f.name)
            if want and have == want:
                fam = 2
            elif want and have and len(min(have, want, key=len)) >= 6 and (
                    have.startswith(want) or want.startswith(have)):
                fam = 1
            else:
                fam = 0
            same = sum(1 for g in f.glyphs if mine.get(g.code) == g.contours) if mine else 0
            if fam == 0 and not (mine and same * 2 > len(mine)):
                continue
            style = int(f.italic == font.italic) + int(f.bold == font.bold)
            # por nombre: estilo y luego el orden de las libs (el mismo de resolve());
            # por contornos: primero cuantos glifos coinciden
            key = (fam, style, -lf.order, same) if fam else (0, same, style, -lf.order)
            if best_key is None or key > best_key:
                best, best_key = f, key
        return best

    def known_names(self) -> List[str]:
        names = set(self.fontmap.keys())
        for lf in self.fonts:
            names.add(lf.export)
            if font_family(lf.font):
                names.add(font_family(lf.font))
        return sorted(n for n in names if n)


def build_fontlib(lib: FontLibrary, out_path: str, compress: bool = True) -> None:
    """Crea gfxfontlib.swf: una DefineFont3 por cada alias "$..." exportada con ese nombre.
    El nombre interno de la fuente es tambien el alias, para que <font face="$Font2">
    funcione tras la importacion."""
    names = set(lib.fontmap.keys())
    for lf in lib.fonts:
        if lf.export.startswith("$"):
            names.add(lf.export)
    tags: List[Tag] = [Tag(69, struct.pack("<I", 0))]   # FileAttributes: AS2 (0x08 = AS3!)
    exports: List[Tuple[int, str]] = []
    next_id = 1
    for name in sorted(names):
        lf = lib.resolve(name)
        if lf is None:
            log("  fontlib: no font for %s" % name)
            continue
        tags.append(encode_any_font(lf.font, next_id, name))
        exports.append((next_id, name))
        log("  fontlib: %-26s <- %-34s (%s)" % (name, font_family(lf.font), lf.lib))
        next_id += 1
    tags.append(Tag(T_EXPORTASSETS, encode_export_assets(exports)))
    tags.append(Tag(T_SHOWFRAME, b""))
    tags.append(Tag(T_END, b""))
    movie = Movie(b"FWS", 8, encode_rect(0, 20, 0, 20), 30 << 8, 1, tags)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(write_movie(movie, compress))
    log("fontlib: %d fonts -> %s" % (len(exports), out_path))


# ===========================================================================
# 4. Conversion de una pelicula
# ===========================================================================
@dataclass
class Options:
    fonts_mode: str = "inline"          # inline | import
    fontlib_url: Optional[str] = None   # para --fonts import: URL que se escribira
    image_format: str = "lossless"      # lossless | png
    compress: bool = True
    font_aliases: bool = True
    force_outlines: bool = True         # campos "de dispositivo" con fuente con glifos -> useOutlines
    gfx_letter_spacing: bool = True     # letterSpacing del HTML sin parte fraccionaria, como GFx
    wrap_space_fix: bool = True         # ensancha los campos con wordWrap lo que mide un espacio
    hide_partial_lines: bool = True     # recorta el alto para no pintar la linea a medias del pie
    geometry_guard: bool = True         # no ensancha (o lo minimo) si el AS lee la caja del campo
    runtime_texts: bool = True          # ancho exacto con los labels que el script pone en el campo
    strings_paths: Optional[List[str]] = None   # tablas de textos (defecto: DEFAULT_STRINGS)
    nbsp_glyph: bool = True             # U+00A0 con el avance del espacio si la fuente no lo trae
    verbose: bool = False


@dataclass
class Stats:
    images: int = 0
    images_scaled: int = 0
    images_missing: List[str] = field(default_factory=list)
    fonts: int = 0
    fonts_inlined: List[str] = field(default_factory=list)
    font_aliases: List[str] = field(default_factory=list)
    dropped: Dict[int, int] = field(default_factory=dict)
    imports_kept: List[str] = field(default_factory=list)
    texts_outlined: int = 0
    texts_kept_device: int = 0          # campos que se dejan sin contornos (fuente sin layout)
    faces_fixed: int = 0
    layouts_synth: List[str] = field(default_factory=list)
    letter_spacing_fixed: int = 0       # valores letterSpacing fraccionarios truncados
    fields_widened: int = 0             # campos wordWrap ensanchados (espacio final de Ruffle)
    fields_not_widened: int = 0         # wordWrap sin ensanchar (borde/fondo o sin espacio)
    paragraph_spaces: int = 0           # espacios anadidos al final de parrafo
    wrap_modes: Dict[str, int] = field(default_factory=dict)   # exacto/base/conflicto/...
    wrap_conflicts: List[str] = field(default_factory=list)    # campos sin ancho exacto posible
    partial_lines_hidden: List[str] = field(default_factory=list)  # campos recortados al pie
    geometry_kept: List[str] = field(default_factory=list)  # ensanchado limitado: el AS lee su caja
    runtime_text_fields: int = 0        # campos con ancho calculado con los labels del script
    nbsp_added: int = 0                 # fuentes a las que se anadio U+00A0


class Converter:
    def __init__(self, textures: TextureResolver, fontlib: Optional[FontLibrary], opts: Options):
        self.textures = textures
        self.fontlib = fontlib
        self.opts = opts
        self.stats = Stats()
        self.image_cache: Dict[int, Image.Image] = {}   # imageID -> imagen a tamano destino
        self.pending_exports: List[Tuple[int, str]] = []

    # ---------------- imagenes ----------------
    def _image_tag(self, char_id: int, img: Image.Image) -> Tag:
        if self.opts.image_format == "png":
            return Tag(T_DEFINEBITSJPEG2, encode_jpeg2_png(char_id, img))
        return Tag(T_DEFINEBITSLOSSLESS2, encode_lossless2(char_id, img))

    def _load_texture(self, export_name: str, file_name: str, tw: int, th: int) -> Image.Image:
        key_file = re.sub(r"\.(dds|tga|png)$", "", file_name, flags=re.I)
        img, src = self.textures.resolve([key_file, export_name])
        if img is None:
            self.stats.images_missing.append(file_name or export_name)
            log("  MISSING texture %r (%r): using a transparent %dx%d bitmap"
                % (file_name, export_name, tw, th))
            return Image.new("RGBA", (max(tw, 1), max(th, 1)), (0, 0, 0, 0))
        if tw and th and img.size != (tw, th):
            if self.opts.verbose:
                log("  rescale %s %dx%d -> %dx%d" % (os.path.basename(src), img.size[0], img.size[1], tw, th))
            img = img.resize((tw, th), Image.LANCZOS)
            self.stats.images_scaled += 1
        return img

    def convert_external_image2(self, data: bytes) -> Optional[Tag]:
        image_id, id_type, _fmt, tw, th = struct.unpack_from("<5H", data, 0)
        export_name, pos = read_netstr(data, 10)
        file_name, pos = read_netstr(data, pos)
        img = self._load_texture(export_name, file_name, tw, th)
        self.image_cache[image_id] = img
        if id_type != 0:
            # no es un caracter (textura de fuente/degradado): solo lo guardamos por si
            # un DefineSubImage lo recorta
            return None
        self.stats.images += 1
        if export_name:
            self.pending_exports.append((image_id, export_name))
        return self._image_tag(image_id, img)

    def convert_external_image(self, data: bytes) -> Tag:
        char_id, _fmt, tw, th = struct.unpack_from("<4H", data, 0)
        export_name, pos = read_netstr(data, 8)
        file_name = export_name
        if pos < len(data):
            file_name, pos = read_netstr(data, pos)
        img = self._load_texture(export_name, file_name, tw, th)
        self.image_cache[char_id] = img
        self.stats.images += 1
        if export_name:
            self.pending_exports.append((char_id, export_name))
        return self._image_tag(char_id, img)

    def convert_sub_image(self, data: bytes) -> Tag:
        char_id, image_id, x1, y1, x2, y2 = struct.unpack_from("<6H", data, 0)
        src = self.image_cache.get(image_id)
        if src is None:
            log("  warning: DefineSubImage %d points to unknown image %d" % (char_id, image_id))
            img = Image.new("RGBA", (max(x2 - x1, 1), max(y2 - y1, 1)), (0, 0, 0, 0))
        else:
            img = src.crop((x1, y1, x2, y2))
        self.stats.images += 1
        return self._image_tag(char_id, img)

    # ---------------- recorrido de etiquetas ----------------
    def _drop(self, code: int) -> None:
        self.stats.dropped[code] = self.stats.dropped.get(code, 0) + 1

    def convert_tags(self, tags: List[Tag]) -> List[Tag]:
        out: List[Tag] = []
        for t in tags:
            c = t.code
            if c == GFX_DEFINEEXTERNALIMAGE2:
                nt = self.convert_external_image2(t.data)
                if nt:
                    out.append(nt)
            elif c == GFX_DEFINEEXTERNALIMAGE:
                out.append(self.convert_external_image(t.data))
            elif c == GFX_DEFINESUBIMAGE:
                out.append(self.convert_sub_image(t.data))
            elif c == GFX_DEFINECOMPACTEDFONT:
                fid, fonts = parse_compacted_font(t.data)
                if len(fonts) > 1:
                    log("  warning: font %d has %d FontType; using the first" % (fid, len(fonts)))
                font = fonts[0]
                lf = None
                if not font.glyphs and font.name and self.fontlib is not None:
                    # fuente "vacia" (solo nombre): el juego la resuelve por nombre en las
                    # font libs; hacemos lo mismo incrustando la fuente real con ese id.
                    lf = self.fontlib.resolve(font.name)
                if lf is not None:
                    self.local_fonts[fid] = lf.font
                    out.append(encode_any_font(lf.font, fid, font.name))
                    self.stats.fonts_inlined.append("%s(vacia)=%s" % (font.name, font_family(lf.font)))
                else:
                    if font.glyphs and not font.has_layout:
                        # sin layout (avances y ascent a 0): se completa con la copia de la
                        # misma familia en las font libs, como la maqueta el juego
                        donor = self.fontlib.layout_donor(font) if self.fontlib is not None else None
                        msg = synthesize_layout(font, donor)
                        self.stats.layouts_synth.append("%d %r: %s" % (fid, font.name, msg))
                        if self.opts.verbose:
                            log("  font %d %r without layout -> %s" % (fid, font.name, msg))
                    if self.opts.nbsp_glyph and ensure_nbsp_glyph(font):
                        self.stats.nbsp_added += 1
                    name = font.name
                    if not name and font.glyphs:
                        # varias fuentes sin nombre en la misma pelicula serian ambiguas para
                        # la busqueda por nombre de Ruffle: nombre sintetico unico
                        name = "gfxfont_%d" % fid
                        self.font_names[fid] = name
                    self.local_fonts[fid] = font
                    out.append(encode_define_font(fid, font, name))
                self.stats.fonts += 1
            elif c in (T_DEFINEFONT2, T_DEFINEFONT3):
                (fid,) = struct.unpack_from("<H", t.data, 0)
                self.local_fonts[fid] = RawFont(c, t.data)
                out.append(t)
            elif c in (GFX_EXPORTERINFO, GFX_FONTTEXTUREINFO, GFX_DEFINEEXTERNALGRADIENT,
                       GFX_DEFINEGRADIENTMAP, GFX_DEFINEEXTERNALSOUND, GFX_DEFINEEXTERNALSTREAMSOUND):
                self._drop(c)
            elif c in (T_IMPORTASSETS, T_IMPORTASSETS2):
                out.extend(self.convert_import(t))
            elif c == T_DEFINEEDITTEXT:
                out.append(Tag(c, self.convert_edit_text(t.data)))
            elif c == T_EXPORTASSETS:
                items = parse_export_assets(t.data)
                for cid, name in items:
                    self.exported[cid] = name
                    self.pending_exports = [(i, n) for (i, n) in self.pending_exports if i != cid]
                out.append(t)
            elif c == T_DEFINESPRITE:
                sid, frames, sub = split_sprite(t.data)
                out.append(Tag(c, join_sprite(sid, frames, self.convert_tags(sub))))
            elif c >= 1000:
                log("  warning: unknown GFx tag %d dropped" % c)
                self._drop(c)
            else:
                out.append(t)
        return out

    def _field_font(self, fid: int) -> Tuple[Optional[str], int, bool]:
        """(nombre con el que Ruffle vera la fuente, n de glifos, tiene layout) para un id
        de fuente."""
        if fid in self.inlined:
            name, lf = self.inlined[fid]
            return name, font_glyph_count(lf.font), font_has_layout(lf.font)
        if fid in self.local_fonts:
            f = self.local_fonts[fid]
            return self.font_names.get(fid, font_family(f)), font_glyph_count(f), font_has_layout(f)
        if fid in self.imported_names:
            return self.imported_names[fid], 1, True   # se resolvera en gfxfontlib.swf
        return None, 0, False

    def _field_font_obj(self, fid: Optional[int]):
        """Fuente (FontData | RawFont) que vera Ruffle para un id de fuente, o None."""
        if fid is None:
            return None
        if fid in self.inlined:
            return self.inlined[fid][1].font
        if fid in self.local_fonts:
            return self.local_fonts[fid]
        if fid in self.imported_names and self.fontlib is not None:
            lf = self.fontlib.resolve(self.imported_names[fid])
            return lf.font if lf else None
        return None

    def _font_by_face(self, face: str):
        """Fuente que Ruffle elegira para <font face="...">: por nombre interno entre las de
        la pelicula; si no esta, la de las font libs (add_font_aliases la anadira)."""
        for fid, f in self.local_fonts.items():
            if font_glyph_count(f) and self.font_names.get(fid, font_family(f)) == face:
                return f
        for cid, (name, lf) in self.inlined.items():
            if name == face:
                return lf.font
        if self.fontlib is not None and face:
            lf = self.fontlib.resolve(face)
            return lf.font if lf else None
        return None

    @staticmethod
    def _run_key(fmt: Dict[str, str]) -> Tuple:
        return tuple(sorted((k, v) for k, v in fmt.items() if k != "align"))

    def _text_format(self, fid: Optional[int], height: Optional[int], html: bool,
                     text: Optional[bytes], align: int):
        """Formato del texto inicial de un campo: (fuente, tamano twips, letterSpacing px,
        kerning, alineacion, parrafos con texto si todo el texto tiene un solo formato,
        todos los parrafos incluidos los vacios -o None si no es de un solo formato-)."""
        font = self._field_font_obj(fid)
        size_tw = height
        ls = 0
        kerning = False
        paras: List[str] = []
        all_paras: Optional[List[str]] = None
        if html and text:
            src = text.decode("utf-8", "replace")
            run = html_dominant_run(src)
            if run:
                if run.get("face"):
                    font = self._font_by_face(run["face"]) or font
                try:
                    size_tw = int(round(float(run["size"]) * 20)) if "size" in run else size_tw
                except ValueError:
                    pass
                try:
                    ls = gfx_letter_spacing(float(run.get("letterspacing", "0")))
                except ValueError:
                    ls = 0
                kerning = run.get("kerning") == "1"
                align = {"left": 0, "right": 1, "center": 2, "justify": 3}.get(run.get("align", ""), align)
                hp = html_paragraphs(src)
                keys = {self._run_key(f) for p in hp for f, t in p if t.strip()}
                if len(keys) == 1:
                    paras = ["".join(t for _, t in p) for p in hp]
                    body = re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", src) or [src]
                    all_paras = []
                    for b in body:
                        for piece in re.split(r"(?i)<br\s*/?>", b):
                            all_paras.append(_html.unescape(re.sub(r"<[^>]+>", "", piece)))
        elif text:
            all_paras = re.split(r"\r\n|\r|\n", text.decode("utf-8", "replace"))
            paras = [p for p in all_paras if p.strip()]
        return font, size_tw, ls, kerning, align, paras, all_paras

    def _partial_line_clip(self, fid: Optional[int], height: Optional[int], html: bool,
                           text: Optional[bytes], align: int, box_w_tw: int, box_h_tw: int,
                           leading_tw: int) -> Optional[int]:
        """GFx no pinta las lineas que no caben enteras en el campo (lossantosfreegans: la
        ultima palabra del titulo de la portada no asoma en las capturas del juego);
        Ruffle las pinta recortadas.  Para texto estatico de un solo formato se calcula en
        que linea corta GFx y se devuelve el alto (twips) que deja esa linea fuera del campo
        en Ruffle (el borde de arriba de la primera linea que GFx no pinta); None si no hay
        linea a medias o no se puede calcular."""
        font, size_tw, ls, kerning, _, paras, all_paras = self._text_format(fid, height, html, text, align)
        if not all_paras or not isinstance(font, FontData) or not size_tw:
            return None
        if html and re.search(rb"(?i)<textformat[^>]*leading", text or b""):
            return None
        m = TextMetrics(font, size_tw, ls * 20, kerning)
        width_tw = box_w_tw - 80
        k = size_tw / float(font.nominal)
        line_h = int(font.ascent * k) + int(font.descent * k)
        dflt = self._field_font_obj(fid)
        if isinstance(dflt, FontData) and height:
            kd = height / float(dflt.nominal)
            empty_h = int(dflt.ascent * kd) + int(dflt.descent * kd)
        else:
            empty_h = line_h
        heights: List[int] = []
        for ptxt in all_paras:
            if not ptxt.strip():
                heights.append(empty_h)
                continue
            lines = gfx_wrap(ptxt.split(" "), m, width_tw)
            if lines is None:
                return None
            heights.extend([line_h] * len(lines))
        inner_bottom = box_h_tw - 40
        top = 40
        for i, h in enumerate(heights):
            if top + h > inner_bottom:
                if i == 0 or top >= box_h_tw:
                    return None          # no se ve ni la primera, o la cortada ya queda fuera
                return top
            top += h + leading_tw
        return None

    def _wrap_extra_twips(self, fid: Optional[int], height: Optional[int], html: bool,
                          text: Optional[bytes], align: int, box_tw: int,
                          margins_tw: int, texts: Optional[list] = None, geo: bool = False,
                          slack: Optional[Tuple[float, float]] = None,
                          box_h_tw: int = 0) -> Tuple[int, int, str]:
        """Cuanto ensanchar un campo wordWrap para que Ruffle parta las lineas como GFx:
        (twips, alineacion dominante, como se calculo).

        Punto robusto (robust_wrap_extra): un espacio con el formato dominante mas 2 x
        letterSpacing (Ruffle mide "palabra + espacio" y pone letterSpacing tras cada glifo;
        GFx no cuenta el espacio final y lo pone solo entre glifos) menos el sesgo esperado del
        redondeo en una linea llena.  Sobre el se eligen:
        - 'exacto': texto inicial de un solo formato y fuente GFx: intervalo exacto de anchos
          con los que Ruffle reproduce las lineas del juego, y dentro, el punto mas cercano al
          robusto (el script puede poner despues otro texto con el mismo formato).
        - 'textos': campos que el script rellena con labels GXT conocidos (nombre de instancia =
          label, SET_TEXT_WITH_TRANSLATION / setLocalisedText): el mismo calculo con cada
          texto en el formato por defecto del campo (fuente y tamano del DefineEditText, sin
          letterSpacing ni kerning, como queda tras htmlText); se cruzan los intervalos.  Los
          textos de un nombre compartido por otros campos solo cuentan si caben en el alto.
        - 'robusto': texto desconocido.
        - 'geo': el AS lee la caja del campo (_width, getBounds; _x si el ensanchado mueve el
          borde izquierdo): el menor ensanchado que da las lineas del juego (0 si ya las da;
          0 si el texto no se conoce), para no cambiar la geometria que el juego usa.
        'slack': holgura (izquierda, derecha) dentro de clips cuya caja lee el AS: el
        ensanchado se queda dentro si las lineas lo permiten.
        Si los intervalos no tienen punto comun, el ancho que cumple mas parrafos."""
        font, size_tw, ls, kerning, align, paras, _ = self._text_format(fid, height, html, text, align)
        if font is None or not size_tw:
            return 0, align, "sin fuente"
        em = font_advance_em(font, 0x20)
        if em is None:
            return 0, align, "sin espacio"       # sin glifo de espacio: Ruffle no lo mide
        width_tw = box_tw - 80 - margins_tw      # gutter de 2 px a cada lado (Flash, GFx, Ruffle)
        robust = robust_wrap_extra(font, size_tw, ls * 20, width_tw) if isinstance(font, FontData) else None
        if robust is None:
            robust = int(em * size_tw) + 2 * ls * 20
        robust = max(0, robust)
        static_iv: List[Tuple[int, int]] = []
        text_iv: List[Tuple[int, int]] = []
        sure_text = False
        if isinstance(font, FontData) and not margins_tw:
            if paras:
                m = TextMetrics(font, size_tw, ls * 20, kerning)
                static_iv.append(ruffle_width_interval(paras, m, width_tw))
            dfont = self._field_font_obj(fid)
            if texts and isinstance(dfont, FontData) and height:
                m = TextMetrics(dfont, height, 0, False)
                k = height / float(dfont.nominal)
                line_h = int(dfont.ascent * k) + int(dfont.descent * k)
                cap = max(1, (box_h_tw - 80) // line_h) if line_h > 0 and box_h_tw else 1 << 30
                for paras_t, sure in texts:
                    tv = []
                    nlines = 0
                    for p in paras_t:
                        if p is None or not p.strip():
                            nlines += 1
                            continue
                        lines = gfx_wrap(p.split(" "), m, width_tw)
                        if lines is None:
                            continue
                        nlines += len(lines)
                        a, b_ = ruffle_width_interval([p], m, width_tw)
                        if a < b_:
                            tv.append((a, b_))
                    if tv and (sure or nlines <= cap):
                        text_iv.extend(tv)
                        sure_text |= sure
        if text_iv:
            self.stats.runtime_text_fields += 1
            # el texto del script sustituye al inicial; si el label es el nombre del campo,
            # el inicial no se llega a ver
            ivals = text_iv if sure_text else static_iv + text_iv
            how = "textos" if sure_text or not static_iv else "exacto+textos"
        else:
            ivals = static_iv
            how = "exacto" if static_iv else "robusto"
        if geo:
            target = width_tw                    # el menor ensanchado que de las lineas
        elif align == 3:
            # justificado: Ruffle estira las lineas hasta el ancho de maquetacion, asi que el
            # borde derecho se mueve con el ensanchado: el minimo que da las lineas del juego
            target = width_tw
        else:
            target = width_tw + robust
        exact = True
        if ivals:
            target, exact = pick_wrap_width(ivals, target)
        extra = max(0, target - width_tw)
        if slack is not None and extra > 0:
            # dentro de un clip cuya caja lee el AS: sin pasar de la holgura si las lineas
            # lo permiten
            room = int({1: slack[0], 2: 2 * min(slack)}.get(align, slack[1]))
            if extra > room:
                if not ivals or all(a <= width_tw + room < b_ for a, b_ in ivals):
                    extra = room
                    how += "+caja"
                else:
                    how += "+caja(excede)"
        if geo:
            how = "geo(%s)" % how
        if not exact:
            how = "conflicto(%s)" % how
        return extra, align, how

    def convert_edit_text(self, data: bytes) -> bytes:
        """Ajustes de DefineEditText para imitar a GFx:
        - GFx no tiene fuentes de dispositivo: si el campo no usa contornos pero su fuente
          trae glifos, se activan (si no, Ruffle usaria una fuente del navegador).  Solo
          si la fuente tiene layout: sin avances Ruffle maquetaria el campo con ancho 0
          (las GFx sin layout ya salen con el suyo sintetizado, ver synthesize_layout).
        - face="" en el HTML inicial (fuentes sin nombre): GFx conserva la fuente del
          campo; se sustituye por el nombre (sintetico) de esa fuente.
        - letterSpacing fraccionario en el HTML inicial: GFx lo aplica sin la parte
          fraccionaria (0.5 -> 0); se deja entero (ver gfx_letter_spacing).
        - wordWrap: Ruffle decide si una palabra cabe midiendo "palabra + espacio"
          (Font::wrap_line, slice word_start..word_end + 1); GFx y Flash no cuentan el
          espacio final.  Asi Ruffle manda a la linea siguiente palabras que en el juego
          caben (swallowco "XS,", vinewoodloglinegenerator "easy.", fruitcomputers "to",
          electrotokesystem "micro-atomization").  Se compensa ensanchando el campo lo que
          mide un espacio con su formato dominante, hacia el lado que no mueve el texto
          (izquierda: a la derecha; derecha: a la izquierda; centro: mitad y mitad), mas dos
          veces el letterSpacing (Ruffle lo suma tambien al ultimo glifo y al espacio; GFx
          solo entre glifos).  No se toca si el campo dibuja borde/fondo.  La ultima
          palabra de cada parrafo Ruffle la mide sin espacio: en texto estatico alineado a la
          izquierda o justificado se le anade uno (append_paragraph_spaces)."""
        rect = decode_rect(data, 2)
        rl = rect_nbytes(data, 2)
        p = 2 + rl
        f1, f2 = data[p], data[p + 1]
        # recorrido del resto de la estructura (SWF DefineEditText)
        q = p + 2
        fid = height = None
        if f1 & 0x01:                                           # HasFont
            (fid,) = struct.unpack_from("<H", data, q)
            q += 2
        if f2 & 0x80:                                           # HasFontClass
            q = data.index(b"\0", q) + 1
        if f1 & 0x01 or f2 & 0x80:
            (height,) = struct.unpack_from("<H", data, q)
            q += 2
        if f1 & 0x04:                                           # HasTextColor
            q += 4
        if f1 & 0x02:                                           # HasMaxLength
            q += 2
        align = 0
        layout_pos = 0
        if f2 & 0x20:                                           # HasLayout
            align = data[q]
            layout_pos = q
            q += 9
        var_end = data.index(b"\0", q)
        has_var = var_end > q
        q = var_end + 1                                         # VariableName
        text = None
        if f1 & 0x80:                                           # HasText (ultimo campo)
            text = data[q:data.index(b"\0", q)]
        head = data[p + 2:q]                                    # fuente ... VariableName
        nf2 = f2
        name = None
        if fid is not None:
            name, glyphs, has_layout = self._field_font(fid)
            if self.opts.force_outlines and not (f2 & 0x01) and glyphs:
                if has_layout:
                    nf2 |= 0x01
                    self.stats.texts_outlined += 1
                else:
                    self.stats.texts_kept_device += 1
        html = bool(f2 & 0x02)
        if text is not None and html and name and re.search(rb'face=""', text, re.I):
            text, n = re.subn(rb'(?i)face=""', b'face="' + name.encode("utf-8") + b'"', text)
            self.stats.faces_fixed += n
        if text and html and self.opts.gfx_letter_spacing and b"letterspacing" in text.lower():
            text, n = truncate_html_letter_spacing(text)
            self.stats.letter_spacing_fixed += n
        rect_b = data[2:p]
        if (f1 & 0x40) and self.opts.wrap_space_fix:            # WordWrap
            if f2 & 0x08:                                       # borde/fondo: no se toca
                self.stats.fields_not_widened += 1
            else:
                # la ultima palabra de cada parrafo Ruffle la mide sin espacio: con el campo
                # ensanchado tendria holgura que el juego no le da.  Un espacio al final del
                # parrafo (invisible a la izquierda/justificado) la iguala.  Solo en texto
                # estatico: ni campos de entrada ni con variable.
                # geometria que el AS usa, textos que el script le pone y holgura en clips
                # cuya caja lee el AS (ver _wrap_extra_twips).  Con la caja leida no se anade
                # el espacio de fin de parrafo: el ensanchado minimo se calcula sin el.
                cid = struct.unpack_from("<H", data)[0]
                geo, props, rtexts = self._field_runtime(cid, align)
                slack = self.field_slack.get(cid) if hasattr(self, "field_slack") else None
                new_text, nsp = text, 0
                if text and (f1 & 0x08) and not has_var and not geo:
                    new_text, nsp = append_paragraph_spaces(text, html, align)
                xmin, xmax, ymin, ymax = rect
                margins = struct.unpack_from("<HH", data, layout_pos + 1) if layout_pos else (0, 0)
                extra, al, how = self._wrap_extra_twips(fid, height, html, new_text, align,
                                                        xmax - xmin, sum(margins), rtexts, geo, slack,
                                                        ymax - ymin)
                self.stats.wrap_modes[how] = self.stats.wrap_modes.get(how, 0) + 1
                if how.startswith("conflicto"):
                    self.stats.wrap_conflicts.append("%d %s %r" % (
                        cid, how, re.sub(r"<[^>]+>", "", (new_text or b"").decode("utf-8", "replace"))[:70]))
                if geo or "caja" in how:
                    self.stats.geometry_kept.append("%d %s %s +%.2fpx %s" % (
                        cid, "/".join(sorted(self.layout.names.get(cid, ()))), how, extra / 20.0,
                        ",".join(sorted(props))))
                if extra > 0 or how.startswith("exacto"):
                    text = new_text
                    self.stats.paragraph_spaces += nsp
                box_w = xmax - xmin
                if extra > 0:
                    if al == 1:
                        xmin -= extra
                    elif al == 2:
                        xmin -= extra // 2
                        xmax += extra - extra // 2
                    else:
                        xmax += extra
                    self.stats.fields_widened += 1
                else:
                    self.stats.fields_not_widened += 1
                # linea a medias al pie: GFx no la pinta (solo texto estatico con las lineas
                # del juego ya garantizadas, multilinea y sin autoSize)
                static_exact = re.fullmatch(r"(geo\()?exacto(\+caja)?\)?", how) is not None
                if (static_exact and self.opts.hide_partial_lines and (f1 & 0x08) and not has_var
                        and (f1 & 0x20) and not (f2 & 0x40)
                        and not props & {"_height", "_yscale", "getBounds", "getRect"}):
                    leading = struct.unpack_from("<h", data, layout_pos + 7)[0] if layout_pos else 0
                    clip = self._partial_line_clip(fid, height, html, text, align, box_w,
                                                   ymax - ymin, leading)
                    if clip is not None:
                        ymax = ymin + clip
                        self.stats.partial_lines_hidden.append("%d %r" % (
                            struct.unpack_from("<H", data)[0],
                            re.sub(r"<[^>]+>", "", text.decode("utf-8", "replace"))[:60]))
                if (xmin, xmax, ymin, ymax) != rect:
                    rect_b = encode_rect(xmin, xmax, ymin, ymax)
        out = data[:2] + rect_b + bytes([f1, nf2]) + head
        if text is not None:
            out += text + b"\0"
        return out

    def convert_import(self, t: Tag) -> List[Tag]:
        url, reserved, items = parse_import_assets(t.code, t.data)
        base = url.replace("\\", "/").split("/")[-1].lower()
        is_fontlib = base in FONTLIB_URLS or base.startswith("font_lib_")
        if not is_fontlib:
            self.stats.imports_kept.append(url)
            return [t]
        if self.opts.fonts_mode == "import" or self.fontlib is None:
            new_url = self.opts.fontlib_url or url
            self.stats.imports_kept.append(new_url)
            for cid, name in items:
                self.imported_names[cid] = name
            return [Tag(t.code, encode_import_assets(t.code, new_url, reserved, items))]
        # inline: sustituye cada importacion por la fuente real con el mismo id
        out: List[Tag] = []
        rest: List[Tuple[int, str]] = []
        for cid, name in items:
            lf = self.fontlib.resolve(name)
            if lf is None:
                log("  warning: no font to import %r; the import is kept" % name)
                rest.append((cid, name))
                continue
            out.append(encode_any_font(lf.font, cid, name))
            self.inlined[cid] = (name, lf)
            self.stats.fonts_inlined.append("%s=%s" % (name, font_family(lf.font)))
        if rest:
            out.append(Tag(t.code, encode_import_assets(t.code, url, reserved, rest)))
            self.stats.imports_kept.append(url)
        return out

    # ---------------- alias de nombres de fuente ----------------
    def add_font_aliases(self, tags: List[Tag], raw_body: bytes) -> List[Tag]:
        """El juego busca fuentes por nombre (face="...", TextFormat.font) en la pelicula
        y en las font libs.  Ruffle solo busca por el nombre interno de las fuentes de la
        pelicula, asi que anadimos copias con los nombres que se usan y no existen."""
        defined = set()
        for fid, f in self.local_fonts.items():
            if font_glyph_count(f) and font_family(f):
                defined.add(font_family(f))
        for cid, (name, lf) in self.inlined.items():
            defined.add(name)
        # candidatos: familias/exports locales, alias importados y todo lo que conoce la lib
        candidates: Dict[str, object] = {}
        for fid, f in self.local_fonts.items():
            exp = self.exported.get(fid)
            if exp and font_glyph_count(f):
                candidates.setdefault(exp, f)
        for cid, (name, lf) in self.inlined.items():
            if font_family(lf.font):
                candidates.setdefault(font_family(lf.font), lf.font)
        if self.fontlib is not None and self.opts.fonts_mode == "inline":
            for n in self.fontlib.known_names():
                if n not in candidates:
                    lf = self.fontlib.resolve(n)
                    if lf is not None:
                        candidates[n] = lf.font
        used_ids = self._used_ids(tags)
        next_id = max(used_ids | {0}) + 1
        extra: List[Tag] = []
        for name, f in sorted(candidates.items()):
            if name in defined or not name:
                continue
            nb = name.encode("utf-8")
            # mencionado en el SWF: FACE="x", 'x', o cadena del pool de constantes
            if not (b'"' + nb + b'"' in raw_body or b"'" + nb + b"'" in raw_body
                    or b"\0" + nb + b"\0" in raw_body):
                continue
            extra.append(encode_any_font(f, next_id, name))
            self.stats.font_aliases.append("%s(id %d)" % (name, next_id))
            defined.add(name)
            next_id += 1
        if not extra:
            return tags
        # se insertan antes del primer ShowFrame (disponibles desde el fotograma 1)
        for i, t in enumerate(tags):
            if t.code == T_SHOWFRAME:
                return tags[:i] + extra + tags[i:]
        return tags + extra

    @staticmethod
    def _used_ids(tags: List[Tag]) -> set:
        ids = set()
        for t in tags:
            if t.code in DEFINE_TAGS and len(t.data) >= 2:
                ids.add(struct.unpack_from("<H", t.data, 0)[0])
            elif t.code in (T_IMPORTASSETS, T_IMPORTASSETS2):
                for cid, _ in parse_import_assets(t.code, t.data)[2]:
                    ids.add(cid)
        return ids

    def _prepare_layout(self, tags: List[Tag]) -> None:
        """Antes de convertir: nombres de instancia de cada caracter, geometria que el AS usa
        y labels que escribe por nombre, holgura de los campos dentro de clips cuya caja lee
        el AS y la tabla de textos del juego."""
        self.layout = MovieLayout(tags)
        self.as_geo, self.as_texts = scan_actionscript(tags)
        # nombres usados por mas de un DefineEditText (btnTxt, heading...): sus labels pueden
        # ser de otro campo con el mismo nombre
        uses: Dict[str, set] = {}
        for cid, names in self.layout.names.items():
            if cid in self.layout.edit_ids:
                for n in names:
                    uses.setdefault(n, set()).add(cid)
        self.shared_names = {n for n, ids in uses.items() if len(ids) > 1}
        self.field_slack: Dict[int, Tuple[float, float]] = {}
        if self.opts.geometry_guard:
            box_read = {"_width", "getBounds", "getRect"}
            clips = {cid for cid, names in self.layout.names.items()
                     if cid in self.layout.sprites and any(self.as_geo.get(n, set()) & box_read for n in names)}
            self.field_slack = self.layout.field_slack(clips)
        self.game_strings = load_game_strings(self.opts.strings_paths) if self.opts.runtime_texts else None

    def _field_runtime(self, cid: int, align: int) -> Tuple[bool, set, list]:
        """(el AS lee o escribe la caja del campo, propiedades, textos que el script le pone):
        textos = [(parrafos, fiable)] de los labels con el nombre del campo (scan_and_set_...:
        fiable) o escritos en 'x.nombre' con SET_TEXT_WITH_TRANSLATION / setLocalisedText (no
        fiable si otro campo comparte el nombre)."""
        names = self.layout.names.get(cid, set()) if hasattr(self, "layout") else set()
        props: set = set()
        for n in names:
            props |= self.as_geo.get(n, set())
        geo = False
        if self.opts.geometry_guard:
            geo = bool(props & {"_width", "getBounds", "getRect"}) or ("_x" in props and align in (1, 2))
        texts: list = []
        st = getattr(self, "game_strings", None)
        if st is not None:
            seen = set()
            for n in sorted(names):
                v = st.lookup(n)
                if v and n not in seen:
                    seen.add(n)
                    texts.append((gxt_paragraphs(v), True))
            for n in sorted(names):
                for lab in sorted(self.as_texts.get(n, ())):
                    v = st.lookup(lab)
                    if v and lab not in seen:
                        seen.add(lab)
                        texts.append((gxt_paragraphs(v), n not in self.shared_names))
        return geo, props, texts

    def convert(self, movie: Movie, raw_body: bytes) -> Movie:
        self.local_fonts: Dict[int, object] = {}
        self.font_names: Dict[int, str] = {}      # id -> nombre sintetico (fuentes sin nombre)
        self.inlined: Dict[int, Tuple[str, LibFont]] = {}
        self.imported_names: Dict[int, str] = {}
        self.exported: Dict[int, str] = {}
        self._prepare_layout(movie.tags)
        tags = self.convert_tags(movie.tags)
        # imagenes cuyo exportName no tenia ExportAssets: se exportan al final del
        # fotograma 1 (antes del primer ShowFrame)
        if self.pending_exports:
            exp = Tag(T_EXPORTASSETS, encode_export_assets(self.pending_exports))
            for i, t in enumerate(tags):
                if t.code == T_SHOWFRAME:
                    tags.insert(i, exp)
                    break
            else:
                tags.append(exp)
        if self.opts.font_aliases:
            tags = self.add_font_aliases(tags, raw_body)
        sig = b"CWS" if self.opts.compress else b"FWS"
        return Movie(sig, movie.version, movie.rect, movie.frame_rate, movie.frame_count, tags)


# Etiquetas donde puede aparecer un nombre de fuente usado en tiempo de ejecucion:
# texto HTML inicial de los campos (FACE="...") y cadenas de ActionScript.
NAME_SCAN_TAGS = {T_DEFINEEDITTEXT, T_DOACTION, T_DOINITACTION, 26, 34, 70}


def name_scan_corpus(tags: List[Tag]) -> bytes:
    parts: List[bytes] = []
    for t in tags:
        if t.code in NAME_SCAN_TAGS:
            parts.append(t.data)
        elif t.code == T_DEFINESPRITE:
            parts.append(name_scan_corpus(split_sprite(t.data)[2]))
    return b"\0".join(parts)


def convert_file(in_path: str, tex_dir: Optional[str], out_path: str, shared_root: Optional[str],
                 opts: Options, fontlib: Optional[FontLibrary]) -> Stats:
    raw = open(in_path, "rb").read()
    movie = read_movie(raw)
    resolver = TextureResolver(tex_dir, shared_root)
    conv = Converter(resolver, fontlib, opts)
    out_movie = conv.convert(movie, name_scan_corpus(movie.tags))
    data = write_movie(out_movie, opts.compress)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(data)
    return conv.stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert GTA V Scaleform GFx movies to SWF for Ruffle.")
    ap.add_argument("input", nargs="?", help=".gfx (or .swf) file")
    ap.add_argument("textures", nargs="?", help="PNG folder of the site .ytd ('-' if none)")
    ap.add_argument("output", nargs="?", help="output .swf")
    ap.add_argument("--shared-png-root", help="root with the other PNG dictionaries (<work>/v/extract/png)")
    ap.add_argument("--fonts", choices=("inline", "import"), default="inline",
                    help="inline: embed the gfxfontlib fonts (default); "
                         "import: keep the ImportAssets2 of gfxfontlib.swf")
    ap.add_argument("--fontlib-url", help="with --fonts import: URL written in the ImportAssets2")
    ap.add_argument("--build-fontlib", metavar="OUT_SWF",
                    help="build the combined font library gfxfontlib.swf and exit")
    ap.add_argument("--extract-root", default=DEFAULT_EXTRACT,
                    help="root of the extracted files (font libraries)")
    ap.add_argument("--image-format", choices=("lossless", "png"), default="lossless",
                    help="lossless: DefineBitsLossless2 (default); png: DefineBitsJPEG2 with a PNG")
    ap.add_argument("--no-compress", action="store_true", help="write an uncompressed FWS")
    ap.add_argument("--no-font-aliases", action="store_true",
                    help="do not add copies of fonts by name")
    ap.add_argument("--keep-device-text", action="store_true",
                    help="do not force useOutlines on device-font text fields")
    ap.add_argument("--keep-letter-spacing", action="store_true",
                    help="do not truncate fractional HTML letterSpacing (GFx truncates it)")
    ap.add_argument("--no-wrap-fix", action="store_true",
                    help="do not widen wordWrap fields for the trailing space Ruffle measures")
    ap.add_argument("--no-geometry-guard", action="store_true",
                    help="also widen the fields whose box the ActionScript reads")
    ap.add_argument("--no-runtime-texts", action="store_true",
                    help="do not use the labels the script puts in the fields for the exact width")
    ap.add_argument("--strings", action="append", metavar="JSON",
                    help="text table label->text (repeatable; default: <work>/v/text/"
                         "strings_web.json and strings_global.json)")
    ap.add_argument("--no-nbsp", action="store_true",
                    help="do not add U+00A0 to the fonts that lack it")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    if a.build_fontlib:
        lib = FontLibrary(a.extract_root, nbsp_glyph=not a.no_nbsp)
        build_fontlib(lib, a.build_fontlib, not a.no_compress)
        return 0
    if not (a.input and a.output):
        ap.error("missing arguments: <in.gfx> <textures_dir> <out.swf>")
    tex = None if a.textures in (None, "-", "") else a.textures
    opts = Options(fonts_mode=a.fonts, fontlib_url=a.fontlib_url, image_format=a.image_format,
                   compress=not a.no_compress, font_aliases=not a.no_font_aliases,
                   force_outlines=not a.keep_device_text, gfx_letter_spacing=not a.keep_letter_spacing,
                   wrap_space_fix=not a.no_wrap_fix, geometry_guard=not a.no_geometry_guard,
                   runtime_texts=not a.no_runtime_texts, strings_paths=a.strings,
                   nbsp_glyph=not a.no_nbsp, verbose=a.verbose)
    fontlib = (FontLibrary(a.extract_root, nbsp_glyph=not a.no_nbsp)
               if (a.fonts == "inline" or opts.font_aliases) else None)
    st = convert_file(a.input, tex, a.output, a.shared_png_root, opts, fontlib)
    log("%s -> %s: %d images (%d rescaled, %d missing), %d fonts, embedded [%s], "
        "aliases [%s], dropped %s, imports %s, fields: %d with forced outlines, %d face=\"\" fixed, "
        "%d letterSpacing truncated, %d wordWrap widened (%d not; mode %s), "
        "%d end-of-paragraph spaces, %d with script texts, %d with the box read by the AS, "
        "%d fonts with U+00A0 added%s%s%s"
        % (os.path.basename(a.input), a.output, st.images, st.images_scaled, len(st.images_missing),
           st.fonts, ", ".join(st.fonts_inlined), ", ".join(st.font_aliases),
           {k: v for k, v in sorted(st.dropped.items())}, st.imports_kept,
           st.texts_outlined, st.faces_fixed, st.letter_spacing_fixed, st.fields_widened,
           st.fields_not_widened, st.wrap_modes, st.paragraph_spaces, st.runtime_text_fields,
           len(st.geometry_kept), st.nbsp_added,
           ", %d device text (font without layout)" % st.texts_kept_device if st.texts_kept_device else "",
           "".join("\n  font without layout %s" % x for x in st.layouts_synth),
           "".join("\n  box read by the AS: %s" % x for x in st.geometry_kept)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
