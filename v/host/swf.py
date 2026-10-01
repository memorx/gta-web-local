"""Minimal tag-level SWF/GFX reader and writer.

Only what the host needs: open a .gfx/.swf (GFX/CFX/FWS/CWS), list tags, insert new
tags and write it back as an uncompressed SWF (FWS). Existing tags are copied byte for byte.

    python v/host/swf.py <file.swf|.gfx> [limit]     dump the tag list
"""
import struct
import zlib

TAG_NAMES = {
    0: 'End', 1: 'ShowFrame', 9: 'SetBackgroundColor', 12: 'DoAction',
    26: 'PlaceObject2', 39: 'DefineSprite', 43: 'FrameLabel', 56: 'ExportAssets',
    57: 'ImportAssets', 59: 'DoInitAction', 69: 'FileAttributes', 71: 'ImportAssets2',
    77: 'Metadata', 1000: 'GFX_ExporterInfo', 1003: 'GFX_DefineExternalGradient',
    1005: 'GFX_DefineCompactedFont', 1009: 'GFX_DefineExternalImage2',
}


class Swf:
    def __init__(self, data: bytes):
        sig = data[:3]
        self.version = data[3]
        body = data[8:]
        if sig in (b'CWS', b'CFX'):
            body = zlib.decompress(body)
        elif sig not in (b'FWS', b'GFX'):
            raise ValueError('unknown signature %r' % sig)
        self.original_sig = sig
        # stage RECT: variable length
        nbits = body[0] >> 3
        rect_len = (5 + 4 * nbits + 7) // 8
        self.rect = body[:rect_len]
        self.frame_rate, self.frame_count = struct.unpack('<HH', body[rect_len:rect_len + 4])
        self.tags = []  # list of (code, body bytes)
        pos = rect_len + 4
        while pos < len(body):
            code_len, = struct.unpack('<H', body[pos:pos + 2]); pos += 2
            code, length = code_len >> 6, code_len & 0x3F
            if length == 0x3F:
                length, = struct.unpack('<I', body[pos:pos + 4]); pos += 4
            self.tags.append((code, body[pos:pos + length]))
            pos += length
            if code == 0:
                break

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read())

    def stage_size(self):
        nbits = self.rect[0] >> 3
        bits = ''.join(f'{b:08b}' for b in self.rect)
        vals, p = [], 5
        for _ in range(4):
            v = int(bits[p:p + nbits], 2); p += nbits
            if v >> (nbits - 1):
                v -= 1 << nbits
            vals.append(v)
        return (vals[1] - vals[0]) / 20, (vals[3] - vals[2]) / 20

    @staticmethod
    def encode_tag(code, body):
        # DoAction/DoInitAction/DefineSprite always use the long header: valid, and it
        # avoids edge cases.
        if len(body) < 0x3F and code not in (12, 59, 39):
            return struct.pack('<H', (code << 6) | len(body)) + body
        return struct.pack('<HI', (code << 6) | 0x3F, len(body)) + body

    def to_bytes(self, compress=False):
        out = bytearray(self.rect)
        out += struct.pack('<HH', self.frame_rate, self.frame_count)
        for code, body in self.tags:
            out += self.encode_tag(code, body)
        if compress:
            payload = zlib.compress(bytes(out), 9)
            return b'CWS' + bytes([self.version]) + struct.pack('<I', len(out) + 8) + payload
        return b'FWS' + bytes([self.version]) + struct.pack('<I', len(out) + 8) + bytes(out)

    def save(self, path, compress=False):
        with open(path, 'wb') as f:
            f.write(self.to_bytes(compress))

    def dump(self, limit=None):
        for i, (code, body) in enumerate(self.tags[:limit]):
            extra = ''
            if code == 59:
                extra = ' sprite=%d' % struct.unpack('<H', body[:2])[0]
            if code == 39:
                extra = ' id=%d' % struct.unpack('<H', body[:2])[0]
            if code in (56, 57, 71):
                extra = ' ' + body[:80].hex()
            print('%4d %-28s len=%-7d%s' % (i, TAG_NAMES.get(code, str(code)), len(body), extra))


if __name__ == '__main__':
    import sys
    s = Swf.load(sys.argv[1])
    print('version', s.version, 'stage', s.stage_size(), 'frames', s.frame_count, 'tags', len(s.tags))
    s.dump(int(sys.argv[2]) if len(sys.argv) > 2 else None)
