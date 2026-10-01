"""Minimal reader for the game's GXT2 text tables.

Format (little endian): '2TXG' | u32 count | count x (u32 hash, u32 offset) | '2TXG' |
u32 size | NUL-terminated UTF-8 strings (offsets are absolute). Hash = joaat(label).
"""
from __future__ import annotations

import os
import struct


def read(path: str) -> dict:
    """{hash: text} of one .gxt2 file."""
    with open(path, 'rb') as fh:
        b = fh.read()
    if b[:4] != b'2TXG':
        raise ValueError('%s: not a GXT2 file' % path)
    count, = struct.unpack_from('<I', b, 4)
    out = {}
    for i in range(count):
        h, off = struct.unpack_from('<II', b, 8 + i * 8)
        end = b.index(b'\0', off)
        out[h] = b[off:end].decode('utf-8', errors='replace')
    return out


def read_block(name: str, base_dir: str, patch_dir: str | None = None) -> dict:
    """A text block (e.g. 'lfi_m') from the base folder, with the patch folder's copy on top."""
    out = read(os.path.join(base_dir, name + '.gxt2'))
    if patch_dir:
        p = os.path.join(patch_dir, name + '.gxt2')
        if os.path.exists(p):
            out.update(read(p))
    return out
