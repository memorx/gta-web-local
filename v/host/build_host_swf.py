"""Builds the browser movie the host drives in Ruffle: web_browser.swf with the host shim.

  input : the game's web_browser .gfx (or the .swf the converter made from it, with the
          images and fonts embedded)
  output: web_browser.swf with the AS2 shim (host_pre.as / host_post.as) injected around the
          frame-1 DoAction that creates the browser ("new ...WEB_BROWSER(this)")

The shim sources are ours (v/host/*.as). They are compiled at build time with JPEXS FFDec
(Java): each .as replaces the DoAction of a one-frame carrier SWF and the compiled action
bytes are cut out of it (<bin_dir>/<name>.bin, reused while the .as does not change).

    python v/host/build_host_swf.py <web_browser.gfx|.swf> <out.swf> --bin-dir <dir> [--recompile]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from swf import Swf  # noqa: E402

SHIM_NAMES = ("host_pre", "host_post")


def _rect(x0, x1, y0, y1):
    vals = [x0, x1, y0, y1]
    nbits = max(v.bit_length() for v in vals) + 1
    bits = format(nbits, '05b') + ''.join(format(v & ((1 << nbits) - 1), '0%db' % nbits) for v in vals)
    bits += '0' * ((8 - len(bits) % 8) % 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def compile_as(name: str, bin_dir: str, ffdec_cmd: list) -> bytes:
    """Compile v/host/<name>.as with JPEXS; keep the DoAction body in <bin_dir>/<name>.bin."""
    os.makedirs(bin_dir, exist_ok=True)
    carrier = Swf.__new__(Swf)
    carrier.version = 8
    carrier.rect = _rect(0, 1280 * 20, 0, 720 * 20)
    carrier.frame_rate = 30 << 8
    carrier.frame_count = 1
    carrier.tags = [(9, b'\xff\xff\xff'), (12, b'\x00'), (1, b''), (0, b'')]
    src = os.path.join(bin_dir, 'carrier.swf')
    dst = os.path.join(bin_dir, 'carrier_%s.swf' % name)
    carrier.save(src)
    if os.path.exists(dst):
        os.remove(dst)
    r = subprocess.run(list(ffdec_cmd) + ['-replace', src, dst, '\\frame_1\\DoAction',
                                          os.path.join(HERE, name + '.as')],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError('JPEXS could not compile %s.as:\n%s' % (name, (r.stdout + r.stderr)[-2000:]))
    out = Swf.load(dst)
    body = [b for c, b in out.tags if c == 12][0]
    with open(os.path.join(bin_dir, name + '.bin'), 'wb') as f:
        f.write(body)
    with open(os.path.join(bin_dir, name + '.src.sha1'), 'w') as f:
        f.write(_sha1(os.path.join(HERE, name + '.as')))
    return body


def _sha1(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def shim_body(name: str, bin_dir: str, ffdec_cmd: list | None, recompile: bool = False) -> bytes:
    """Compiled body of a shim part; recompiled when its .as changed (needs ffdec_cmd)."""
    path = os.path.join(bin_dir, name + '.bin')
    stamp = os.path.join(bin_dir, name + '.src.sha1')
    fresh = (os.path.exists(path) and os.path.exists(stamp)
             and open(stamp).read().strip() == _sha1(os.path.join(HERE, name + '.as')))
    if recompile or not fresh:
        if not ffdec_cmd:
            raise RuntimeError('the host shim must be compiled: JPEXS FFDec (java) is needed')
        return compile_as(name, bin_dir, ffdec_cmd)
    with open(path, 'rb') as f:
        return f.read()


def build(inp: str, outp: str, bin_dir: str, ffdec_cmd: list | None = None, recompile: bool = False) -> None:
    s = Swf.load(inp)
    pre = shim_body('host_pre', bin_dir, ffdec_cmd, recompile)
    post = shim_body('host_post', bin_dir, ffdec_cmd, recompile)
    # The frame-1 DoAction of the main timeline creates the browser
    # ("var TIMELINE = new com.rockstargames.gtav.web.WEB_BROWSER(this)").
    idx = None
    for i, (code, body) in enumerate(s.tags):
        if code == 12 and b'WEB_BROWSER' in body:
            idx = i
            break
        if code == 1:  # ShowFrame: frame 1 ended without it
            break
    if idx is None:
        raise SystemExit('the browser DoAction was not found in frame 1 of %s' % inp)
    if any(code == 12 and b'__HOST' in body for code, body in s.tags):
        raise SystemExit('%s already carries the host shim' % inp)
    s.tags[idx:idx + 1] = [(12, pre), s.tags[idx], (12, post)]
    s.save(outp)
    w, h = s.stage_size()
    print('ok: %s  (%dx%d, shim pre=%dB post=%dB)' % (outp, w, h, len(pre), len(post)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Inject the host shim into the game browser movie.')
    ap.add_argument('input', help="the game's web_browser .gfx or .swf")
    ap.add_argument('output', help='web_browser.swf to write')
    ap.add_argument('--bin-dir', required=True, help='folder for the compiled shim (.bin)')
    ap.add_argument('--ffdec', nargs='+', help='command that runs ffdec-cli (java -jar .../ffdec-cli.jar)')
    ap.add_argument('--recompile', action='store_true')
    a = ap.parse_args(argv)
    build(a.input, a.output, a.bin_dir, a.ffdec, a.recompile)
    return 0


if __name__ == '__main__':
    sys.exit(main())
