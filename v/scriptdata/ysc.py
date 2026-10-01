"""GTA V compiled scripts (.ysc): loader, disassembler, function index and a small VM.

Only what the web-data ports need: read the user's own ``appinternet.ysc`` and run a
few of its pure functions (price tables, news tables, Lifeinvader tables...).

Supported containers
    RSC7 version 10 (Legacy) and version 12 (Enhanced). Both use the same header offsets
    and 0x4000-byte code/string pages; the payload is raw deflate after the 16-byte
    RSC7 header.

Opcode tables
    OLD  the 2013 table (127 opcodes), used by the base scripts in x64b.rpf.
    NEW  later builds: STATIC_U24, STATIC_U24_LOAD, STATIC_U24_STORE inserted after CALL
         (so everything from GLOBAL_U24 on moves up by 3) and IS_BIT_SET = 130.
    The table is detected by decoding the whole code with each table and keeping the one
    that decodes without unknown opcodes and whose CALL targets all land on ENTER.

Usage
    python ysc.py <script.ysc> <out.asm>     one instruction per line, "== func_<n> @<offset> =="
"""
from __future__ import annotations

import math
import struct
import sys
import zlib

_BASE_OPS = [
    ('NOP', 0), ('IADD', 0), ('ISUB', 0), ('IMUL', 0), ('IDIV', 0), ('IMOD', 0), ('INOT', 0), ('INEG', 0),
    ('IEQ', 0), ('INE', 0), ('IGT', 0), ('IGE', 0), ('ILT', 0), ('ILE', 0),
    ('FADD', 0), ('FSUB', 0), ('FMUL', 0), ('FDIV', 0), ('FMOD', 0), ('FNEG', 0),
    ('FEQ', 0), ('FNE', 0), ('FGT', 0), ('FGE', 0), ('FLT', 0), ('FLE', 0),
    ('VADD', 0), ('VSUB', 0), ('VMUL', 0), ('VDIV', 0), ('VNEG', 0),
    ('IAND', 0), ('IOR', 0), ('IXOR', 0), ('I2F', 0), ('F2I', 0), ('F2V', 0),
    ('PUSH_U8', 'b'), ('PUSH_U8_U8', 'bb'), ('PUSH_U8_U8_U8', 'bbb'), ('PUSH_U32', 'I'), ('PUSH_F', 'f'),
    ('DUP', 0), ('DROP', 0), ('NATIVE', 'native'), ('ENTER', 'enter'), ('LEAVE', 'bb'),
    ('LOAD', 0), ('STORE', 0), ('STORE_REV', 0), ('LOAD_N', 0), ('STORE_N', 0),
    ('ARRAY_U8', 'b'), ('ARRAY_U8_LOAD', 'b'), ('ARRAY_U8_STORE', 'b'),
    ('LOCAL_U8', 'b'), ('LOCAL_U8_LOAD', 'b'), ('LOCAL_U8_STORE', 'b'),
    ('STATIC_U8', 'b'), ('STATIC_U8_LOAD', 'b'), ('STATIC_U8_STORE', 'b'),
    ('IADD_U8', 'b'), ('IMUL_U8', 'b'), ('IOFFSET', 0), ('IOFFSET_U8', 'b'), ('IOFFSET_U8_LOAD', 'b'),
    ('IOFFSET_U8_STORE', 'b'), ('PUSH_S16', 'h'), ('IADD_S16', 'h'), ('IMUL_S16', 'h'), ('IOFFSET_S16', 'h'),
    ('IOFFSET_S16_LOAD', 'h'), ('IOFFSET_S16_STORE', 'h'), ('ARRAY_U16', 'H'), ('ARRAY_U16_LOAD', 'H'),
    ('ARRAY_U16_STORE', 'H'), ('LOCAL_U16', 'H'), ('LOCAL_U16_LOAD', 'H'), ('LOCAL_U16_STORE', 'H'),
    ('STATIC_U16', 'H'), ('STATIC_U16_LOAD', 'H'), ('STATIC_U16_STORE', 'H'), ('GLOBAL_U16', 'H'),
    ('GLOBAL_U16_LOAD', 'H'), ('GLOBAL_U16_STORE', 'H'),
    ('J', 'j'), ('JZ', 'j'), ('IEQ_JZ', 'j'), ('INE_JZ', 'j'), ('IGT_JZ', 'j'), ('IGE_JZ', 'j'),
    ('ILT_JZ', 'j'), ('ILE_JZ', 'j'), ('CALL', 'u24'),
]
_TAIL_OPS = [
    ('GLOBAL_U24', 'u24'), ('GLOBAL_U24_LOAD', 'u24'),
    ('GLOBAL_U24_STORE', 'u24'), ('PUSH_U24', 'u24'), ('SWITCH', 'switch'), ('STRING', 0), ('STRINGHASH', 0),
    ('TEXT_LABEL_ASSIGN_STRING', 'b'), ('TEXT_LABEL_ASSIGN_INT', 'b'), ('TEXT_LABEL_APPEND_STRING', 'b'),
    ('TEXT_LABEL_APPEND_INT', 'b'), ('TEXT_LABEL_COPY', 0), ('CATCH', 0), ('THROW', 0), ('CALLINDIRECT', 0),
    ('PUSH_M1', 0), ('PUSH_0', 0), ('PUSH_1', 0), ('PUSH_2', 0), ('PUSH_3', 0), ('PUSH_4', 0), ('PUSH_5', 0),
    ('PUSH_6', 0), ('PUSH_7', 0), ('PUSH_FM1', 0), ('PUSH_F0', 0), ('PUSH_F1', 0), ('PUSH_F2', 0),
    ('PUSH_F3', 0), ('PUSH_F4', 0), ('PUSH_F5', 0), ('PUSH_F6', 0), ('PUSH_F7', 0),
]
OLD_OPS = _BASE_OPS + _TAIL_OPS
NEW_OPS = _BASE_OPS + [('STATIC_U24', 'u24'), ('STATIC_U24_LOAD', 'u24'), ('STATIC_U24_STORE', 'u24')] \
    + _TAIL_OPS + [('IS_BIT_SET', 0)]
TABLES = {'old': OLD_OPS, 'new': NEW_OPS}

# operand sizes that do not depend on the bytes (switch/enter are variable)
_FIXED = {0: 0, 'b': 1, 'bb': 2, 'bbb': 3, 'I': 4, 'f': 4, 'h': 2, 'H': 2, 'j': 2, 'u24': 3, 'native': 3}
_PUSH_INT = {'PUSH_U8', 'PUSH_S16', 'PUSH_U24', 'PUSH_U32', 'PUSH_U8_U8', 'PUSH_U8_U8_U8'}


def load(path: str) -> tuple[int, bytes]:
    with open(path, 'rb') as fh:
        raw = fh.read()
    if raw[:4] != b'RSC7':
        raise ValueError('%s: not an RSC7 resource' % path)
    ver = struct.unpack_from('<I', raw, 4)[0]
    return ver, zlib.decompressobj(-15).decompress(raw[16:])


def _ptr(v: int) -> int:
    if v >> 28 not in (5, 6):
        raise ValueError('bad resource pointer %X' % v)
    return v & 0x0FFFFFFF


class Instr:
    __slots__ = ('off', 'name', 'args', 'size')

    def __init__(self, off, name, args, size):
        self.off, self.name, self.args, self.size = off, name, args, size

    def __repr__(self):
        return '%06X %s %r' % (self.off, self.name, self.args)


class Function:
    """One ENTER..(next ENTER) block with what it references."""
    __slots__ = ('index', 'off', 'end', 'nparams', 'frame', 'nret', 'strings', 'calls', 'natives')

    def __init__(self, index, off, nparams, frame):
        self.index, self.off, self.nparams, self.frame = index, off, nparams, frame
        self.end = off
        self.nret = 0
        self.strings: list[str] = []
        self.calls: list[int] = []
        self.natives: list[int] = []

    def __repr__(self):
        return '<func #%d @%X params=%d ret=%d>' % (self.index, self.off, self.nparams, self.nret)


class Script:
    def __init__(self, path: str, table: str | None = None):
        self.path = path
        self.ver, d = load(path)
        u32 = lambda o: struct.unpack_from('<I', d, o)[0]  # noqa: E731
        u64 = lambda o: struct.unpack_from('<Q', d, o)[0]  # noqa: E731
        self.code_size = u32(0x1C)
        self.statics_n = u32(0x24)
        self.natives_n = u32(0x2C)
        statics_p = _ptr(u64(0x30))
        natives_p = _ptr(u64(0x40))
        self.strings_size = u32(0x70)
        self.name = d[_ptr(u64(0x60)):].split(b'\0')[0].decode('latin-1')
        self.code = self._pages(d, _ptr(u64(0x10)), self.code_size)
        self.strings = self._pages(d, _ptr(u64(0x68)), self.strings_size)
        self.natives = []
        for i in range(self.natives_n):
            h = u64(natives_p + 8 * i)
            rot = (self.code_size + i) & 63
            if rot:
                h = ((h << rot) | (h >> (64 - rot))) & 0xFFFFFFFFFFFFFFFF
            self.natives.append(h)
        self.statics = [struct.unpack_from('<q', d, statics_p + 8 * i)[0] for i in range(self.statics_n)]
        self.table_name = table or self.detect_table()
        self.ops = TABLES[self.table_name]
        self._instrs: list[Instr] | None = None
        self._funcs: list[Function] | None = None

    @staticmethod
    def _pages(d: bytes, blocks: int, size: int) -> bytes:
        out = bytearray()
        n = (size + 0x3FFF) >> 14
        for i in range(n):
            p = _ptr(struct.unpack_from('<Q', d, blocks + 8 * i)[0])
            out += d[p:p + (0x4000 if i < n - 1 else size - 0x4000 * (n - 1))]
        return bytes(out)

    # ---- decoding -------------------------------------------------------------------
    def string(self, off: int) -> str | None:
        if not isinstance(off, int) or off < 0 or off >= len(self.strings):
            return None
        return self.strings[off:].split(b'\0')[0].decode('latin-1')

    def _decode(self, ops, strict=True):
        c = self.code
        n = len(c)
        i = 0
        out = []
        while i < n:
            op = c[i]
            start = i
            if op >= len(ops):
                if strict:
                    raise ValueError('unknown opcode %d at %X' % (op, i))
                out.append(Instr(start, '??%d' % op, (), 1))
                i += 1
                continue
            name, fmt = ops[op]
            i += 1
            if fmt == 0:
                args = ()
            elif fmt == 'b':
                args = (c[i],)
            elif fmt == 'bb':
                args = (c[i], c[i + 1])
            elif fmt == 'bbb':
                args = (c[i], c[i + 1], c[i + 2])
            elif fmt == 'I':
                args = struct.unpack_from('<I', c, i)
            elif fmt == 'f':
                args = struct.unpack_from('<f', c, i)
            elif fmt == 'h':
                args = struct.unpack_from('<h', c, i)
            elif fmt == 'H':
                args = struct.unpack_from('<H', c, i)
            elif fmt == 'j':
                args = (i + 2 + struct.unpack_from('<h', c, i)[0],)
            elif fmt == 'u24':
                args = (c[i] | c[i + 1] << 8 | c[i + 2] << 16,)
            elif fmt == 'native':
                b = c[i]
                args = (b >> 2, b & 3, c[i + 1] << 8 | c[i + 2])
            elif fmt == 'enter':
                nl = c[i + 3]
                args = (c[i], struct.unpack_from('<H', c, i + 1)[0], c[i + 4:i + 4 + nl])
                i += 4 + nl
                out.append(Instr(start, name, args, i - start))
                continue
            elif fmt == 'switch':
                cnt = c[i]
                i += 1
                cases = []
                for _ in range(cnt):
                    v, off = struct.unpack_from('<Ih', c, i)
                    i += 6
                    cases.append((v, i + off))
                out.append(Instr(start, name, (cases,), i - start))
                continue
            i += _FIXED[fmt]
            out.append(Instr(start, name, args, i - start))
        return out

    def detect_table(self) -> str:
        """Pick the opcode table that decodes the code consistently."""
        best, score = None, None
        for tname, ops in TABLES.items():
            try:
                ins = self._decode(ops, strict=True)
            except (ValueError, IndexError, struct.error):
                continue
            enters = {x.off for x in ins if x.name == 'ENTER'}
            calls = [x.args[0] for x in ins if x.name == 'CALL']
            bad = sum(1 for t in calls if not self._lands_on_enter(t, enters))
            s = (bad, -len(enters))
            if score is None or s < score:
                best, score = tname, s
        if best is None or score[0] > 0:
            raise ValueError('%s: no opcode table decodes this script consistently' % self.path)
        return best

    def _skip_padding(self, t: int) -> int:
        """Follow the page-end padding a CALL may target (NOPs and a short forward J)."""
        c = self.code
        for _ in range(16):
            if t >= len(c):
                return t
            if c[t] == 0:                      # NOP
                t += 1
            elif c[t] == 85 and t + 2 < len(c):  # J (same number in both tables)
                off = struct.unpack_from('<h', c, t + 1)[0]
                if not 0 <= off < 16:
                    return t
                t = t + 3 + off
            else:
                return t
        return t

    def _lands_on_enter(self, t: int, enters: set) -> bool:
        return t in enters or self._skip_padding(t) in enters

    @property
    def instrs(self) -> list[Instr]:
        if self._instrs is None:
            self._instrs = self._decode(self.ops)
        return self._instrs

    @property
    def functions(self) -> list[Function]:
        """All functions in code order, with the strings, calls and natives they reference."""
        if self._funcs is not None:
            return self._funcs
        funcs: list[Function] = []
        cur = None
        last = None
        for x in self.instrs:
            if x.name == 'ENTER':
                if cur:
                    cur.end = x.off
                cur = Function(len(funcs), x.off, x.args[0], x.args[1])
                funcs.append(cur)
            elif cur is None:
                continue
            elif x.name == 'LEAVE':
                cur.nret = max(cur.nret, x.args[1])
            elif x.name == 'CALL':
                cur.calls.append(self.resolve(x.args[0]))
            elif x.name == 'NATIVE':
                cur.natives.append(x.args[2])
            elif x.name == 'STRING' and last is not None:
                s = self.string(last)
                if s is not None:
                    cur.strings.append(s)
            last = _push_value(x)
        if cur:
            cur.end = len(self.code)
        self._funcs = funcs
        self._by_off = {f.off: f for f in funcs}
        return funcs

    def resolve(self, t: int) -> int:
        """Offset of the ENTER a CALL target reaches (skipping page-end NOP padding)."""
        c = self.code
        k = self._skip_padding(t)
        return k if k < len(c) and self.ops[c[k]][0] == 'ENTER' else t

    def func_at(self, off: int) -> Function:
        self.functions
        return self._by_off[self.resolve(off)]

    def body(self, f: Function) -> list[Instr]:
        """Instructions of one function (binary search over the decoded list)."""
        ins = self.instrs
        lo, hi = 0, len(ins)
        while lo < hi:
            mid = (lo + hi) // 2
            if ins[mid].off < f.off:
                lo = mid + 1
            else:
                hi = mid
        out = []
        for x in ins[lo:]:
            if x.off >= f.end:
                break
            out.append(x)
        return out

    def callers(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for f in self.functions:
            for t in f.calls:
                out.setdefault(t, []).append(f.off)
        return out


def _push_value(x: Instr):
    if x.name in _PUSH_INT:
        return x.args[-1]
    if x.name.startswith('PUSH_') and x.name[5:].isdigit():
        return int(x.name[5:])
    if x.name == 'PUSH_M1':
        return -1
    return None


# ---- virtual machine --------------------------------------------------------------------
class Ptr:
    """Pointer = (memory, cell index). Memory is a frame/static list or the globals dict."""
    __slots__ = ('mem', 'i')

    def __init__(self, mem, i):
        self.mem, self.i = mem, i

    def get(self):
        m = self.mem
        if isinstance(m, dict):
            return m.get(self.i, 0)
        return m[self.i] if 0 <= self.i < len(m) else 0

    def set(self, v):
        m = self.mem
        if isinstance(m, dict):
            m[self.i] = v
        else:
            if self.i >= len(m):
                m.extend([0] * (self.i + 1 - len(m)))
            m[self.i] = v

    def add(self, n):
        return Ptr(self.mem, self.i + int(n))

    def __eq__(self, other):
        return isinstance(other, Ptr) and other.mem is self.mem and other.i == self.i

    def __hash__(self):
        return hash((id(self.mem), self.i))

    def __repr__(self):
        return '<ptr %s+%d>' % (type(self.mem).__name__, self.i)


class Str:
    """A string value (char* or the contents of a text label buffer)."""
    __slots__ = ('s',)

    def __init__(self, s):
        self.s = s

    def __eq__(self, other):
        return isinstance(other, Str) and other.s == self.s

    def __hash__(self):
        return hash(self.s)

    def __repr__(self):
        return 'Str(%r)' % self.s


def as_text(v) -> str | None:
    """Text of a Str, of a pointer to a text label, or None."""
    if isinstance(v, Ptr):
        v = v.get()
    if isinstance(v, Str):
        return v.s
    return None


def i32(v):
    v = int(v) & 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def joaat(s: str) -> int:
    h = 0
    for ch in s.lower().encode('latin-1'):
        h = (h + ch) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    return (h + (h << 15)) & 0xFFFFFFFF


def hook(nparams, nret=1):
    """Decorator for a Python replacement of a script function (VM.hooks[offset] = fn)."""
    def deco(fn):
        fn.nparams, fn.nret = nparams, nret
        return fn
    return deco


class VMError(RuntimeError):
    pass


def _round(f):
    f = float(f)
    return int(math.floor(f + 0.5)) if f >= 0 else -int(math.floor(-f + 0.5))


# SYSTEM math natives keep their original hashes in every edition (checked in the Legacy
# base scripts and in Enhanced), so they can be recognised by hash.
SYSTEM_NATIVES = {
    0xBBDA792448DB5A89: lambda v: float(v),                    # TO_FLOAT
    0xF2DB717A73826179: _round,                                # ROUND
    0xF34EE736CF047844: lambda f: int(math.floor(float(f))),   # FLOOR
    0x11E019C8F43ACC8A: lambda f: int(math.ceil(float(f))),    # CEIL
}


def _cmp(k, a, b):
    if k == 'EQ':
        return a == b
    if k == 'NE':
        return a != b
    if isinstance(a, (Ptr, Str)) or isinstance(b, (Ptr, Str)):
        return False
    if k == 'GT':
        return a > b
    if k == 'GE':
        return a >= b
    if k == 'LT':
        return a < b
    return a <= b


class VM:
    """Runs script functions. Globals default to 0; natives are resolved by `natives`
    (index or hash -> value or callable) and `on_native(index, args, nret)` for the rest."""

    def __init__(self, script: Script, globals_=None, natives=None, hooks=None, on_native=None,
                 max_steps=20_000_000):
        self.s = script
        self.code = script.code
        self.statics = list(script.statics)
        self.globals = globals_ if globals_ is not None else {}
        self.natives = natives or {}
        self.hooks = hooks or {}
        self.on_native = on_native
        self.max_steps = max_steps
        self.steps = 0
        # [(start, end, value)]: IS_BIT_SET opcodes inside [start, end) return `value`
        self.bit_override: list = []
        self.trace: list | None = None      # CALL targets, for debugging
        # decoded instructions by offset (fast dispatch), shared by every VM of this script
        at = getattr(script, '_at', None)
        if at is None:
            at = script._at = {x.off: x for x in script.instrs}
        self._at = at

    def call(self, addr, *args):
        """Run the function starting at `addr` (its ENTER) and return its value(s)."""
        return self._run(addr, list(args))

    def _native(self, idx, args, nret):
        h = self.s.natives[idx]
        v = self.natives.get(idx, self.natives.get(h))
        if v is None:
            v = SYSTEM_NATIVES.get(h)
        if v is None and self.on_native:
            v = self.on_native(idx, args, nret)
        if callable(v):
            v = v(*args)
        return 0 if v is None else v

    def _run(self, entry, stack):
        at = self._at
        frames = []
        pc = entry
        frame = None
        stack.append(('ret', -1))
        steps = 0
        while True:
            steps += 1
            if steps > self.max_steps:
                raise VMError('step limit reached')
            x = at.get(pc)
            if x is None:
                raise VMError('jump into the middle of an instruction at %X' % pc)
            name = x.name
            a = x.args
            pc = x.off + x.size
            if name == 'ENTER':
                params, size = a[0], a[1]
                ret = stack.pop()
                ps = stack[len(stack) - params:] if params else []
                if params:
                    del stack[len(stack) - params:]
                fr = ps + [ret, 0] + [0] * max(0, size - params - 2)
                frames.append((frame, ret))
                frame = fr
                continue
            if name == 'LEAVE':
                nret = a[1]
                rets = stack[len(stack) - nret:] if nret else []
                if nret:
                    del stack[len(stack) - nret:]
                prev, ret = frames.pop()
                frame = prev
                if ret == ('ret', -1):
                    self.steps += steps
                    if nret == 0:
                        return None
                    return rets[0] if nret == 1 else rets
                stack.extend(rets)
                pc = ret[1]
                continue
            if name == 'CALL' or name == 'CALLINDIRECT':
                target = a[0] if name == 'CALL' else stack.pop()
                if self.trace is not None:
                    self.trace.append(target)
                h = self.hooks.get(target)
                if h is not None:
                    n = h.nparams
                    args = stack[len(stack) - n:] if n else []
                    if n:
                        del stack[len(stack) - n:]
                    v = h(*args)
                    if h.nret == 1:
                        stack.append(v)
                    elif h.nret > 1:
                        stack.extend(v)
                    continue
                stack.append(('ret', pc))
                pc = target
                continue
            if name.startswith('PUSH_'):
                if name in _PUSH_INT:
                    if name == 'PUSH_U8_U8' or name == 'PUSH_U8_U8_U8':
                        stack.extend(a)
                    elif name == 'PUSH_U32':
                        stack.append(i32(a[0]))
                    else:
                        stack.append(a[0])
                elif name == 'PUSH_F':
                    stack.append(a[0])
                elif name == 'PUSH_M1':
                    stack.append(-1)
                elif name == 'PUSH_FM1':
                    stack.append(-1.0)
                elif name.startswith('PUSH_F'):
                    stack.append(float(int(name[6:])))
                else:
                    stack.append(int(name[5:]))
                continue
            if name == 'NATIVE':
                nargs, nret, idx = a
                args = stack[len(stack) - nargs:] if nargs else []
                if nargs:
                    del stack[len(stack) - nargs:]
                v = self._native(idx, args, nret)
                if nret:
                    if isinstance(v, (list, tuple)):
                        stack.extend(list(v)[:nret])
                    else:
                        stack.extend([v] + [0] * (nret - 1))
                continue
            if name == 'SWITCH':
                v = stack.pop()
                for cv, target in a[0]:
                    if i32(cv) == v:
                        pc = target
                        break
                continue
            if name in ('IADD', 'ISUB', 'IMUL', 'IDIV', 'IMOD', 'IAND', 'IOR', 'IXOR'):
                b = stack.pop()
                q = stack.pop()
                if isinstance(q, Ptr):
                    if name == 'IADD':
                        stack.append(q.add(b))
                        continue
                    raise VMError('pointer arithmetic %s at %X' % (name, x.off))
                if name == 'IADD':
                    r = q + b
                elif name == 'ISUB':
                    r = q - b
                elif name == 'IMUL':
                    r = q * b
                elif name == 'IDIV':
                    r = int(q / b) if b else 0
                elif name == 'IMOD':
                    r = (abs(q) % abs(b)) * (1 if q >= 0 else -1) if b else 0
                elif name == 'IAND':
                    r = q & b
                elif name == 'IOR':
                    r = q | b
                else:
                    r = q ^ b
                stack.append(i32(r))
                continue
            if name == 'INOT':
                stack.append(0 if stack.pop() else 1)
                continue
            if name == 'INEG':
                stack.append(i32(-stack.pop()))
                continue
            if name in ('IEQ', 'INE', 'IGT', 'IGE', 'ILT', 'ILE', 'FEQ', 'FNE', 'FGT', 'FGE', 'FLT', 'FLE'):
                b = stack.pop()
                q = stack.pop()
                stack.append(1 if _cmp(name[1:], q, b) else 0)
                continue
            if name in ('FADD', 'FSUB', 'FMUL', 'FDIV', 'FMOD'):
                b = float(stack.pop())
                q = float(stack.pop())
                if name == 'FADD':
                    r = q + b
                elif name == 'FSUB':
                    r = q - b
                elif name == 'FMUL':
                    r = q * b
                elif name == 'FDIV':
                    r = q / b if b else 0.0
                else:
                    r = (q - b * int(q / b)) if b else 0.0
                stack.append(r)
                continue
            if name == 'FNEG':
                stack.append(-float(stack.pop()))
                continue
            if name in ('VADD', 'VSUB', 'VMUL', 'VDIV'):
                b = [stack.pop() for _ in range(3)][::-1]
                q = [stack.pop() for _ in range(3)][::-1]
                for u, w in zip(q, b):
                    if name == 'VADD':
                        stack.append(u + w)
                    elif name == 'VSUB':
                        stack.append(u - w)
                    elif name == 'VMUL':
                        stack.append(u * w)
                    else:
                        stack.append(u / w if w else 0.0)
                continue
            if name == 'VNEG':
                v = [stack.pop() for _ in range(3)][::-1]
                stack.extend(-u for u in v)
                continue
            if name == 'I2F':
                stack.append(float(stack.pop()))
                continue
            if name == 'F2I':
                stack.append(int(stack.pop()))
                continue
            if name == 'F2V':
                v = stack.pop()
                stack.extend([v, v, v])
                continue
            if name == 'DUP':
                stack.append(stack[-1])
                continue
            if name == 'DROP':
                stack.pop()
                continue
            if name == 'NOP':
                continue
            if name == 'J':
                pc = a[0]
                continue
            if name == 'JZ':
                if not stack.pop():
                    pc = a[0]
                continue
            if name.endswith('_JZ'):
                b = stack.pop()
                q = stack.pop()
                if not _cmp(name[1:3], q, b):
                    pc = a[0]
                continue
            if name == 'IS_BIT_SET':
                b = stack.pop()
                v = stack.pop()
                forced = None
                for lo, hi, val in self.bit_override:
                    if lo <= x.off < hi:
                        forced = val
                        break
                if forced is not None:
                    stack.append(forced)
                else:
                    stack.append((int(v) >> int(b)) & 1 if isinstance(v, int) else 0)
                continue
            if name.startswith(('LOCAL_', 'STATIC_', 'GLOBAL_')):
                if name.startswith('LOCAL_'):
                    p = Ptr(frame, a[0])
                elif name.startswith('STATIC_'):
                    p = Ptr(self.statics, a[0])
                else:
                    p = Ptr(self.globals, a[0])
                if name.endswith('_LOAD'):
                    stack.append(p.get())
                elif name.endswith('_STORE'):
                    p.set(stack.pop())
                else:
                    stack.append(p)
                continue
            if name == 'LOAD':
                stack.append(stack.pop().get())
                continue
            if name == 'STORE':
                p = stack.pop()
                p.set(stack.pop())
                continue
            if name == 'STORE_REV':
                v = stack.pop()
                stack[-1].set(v)
                continue
            if name == 'LOAD_N':
                p = stack.pop()
                n = stack.pop()
                stack.extend(p.add(k).get() for k in range(n))
                continue
            if name == 'STORE_N':
                p = stack.pop()
                n = stack.pop()
                vals = stack[len(stack) - n:]
                del stack[len(stack) - n:]
                for k, v in enumerate(vals):
                    p.add(k).set(v)
                continue
            if name == 'IOFFSET':
                off = stack.pop()
                stack.append(stack.pop().add(off))
                continue
            if name.startswith('IOFFSET_'):
                p = stack.pop().add(a[0])
                if name.endswith('_LOAD'):
                    stack.append(p.get())
                elif name.endswith('_STORE'):
                    p.set(stack.pop())
                else:
                    stack.append(p)
                continue
            if name in ('IADD_U8', 'IADD_S16'):
                q = stack.pop()
                stack.append(q.add(a[0]) if isinstance(q, Ptr) else i32(q + a[0]))
                continue
            if name in ('IMUL_U8', 'IMUL_S16'):
                stack.append(i32(stack.pop() * a[0]))
                continue
            if name.startswith('ARRAY_'):
                base = stack.pop()
                idx = stack.pop()
                p = base.add(1 + idx * a[0])
                if name.endswith('_LOAD'):
                    stack.append(p.get())
                elif name.endswith('_STORE'):
                    p.set(stack.pop())
                else:
                    stack.append(p)
                continue
            if name == 'STRING':
                stack.append(Str(self.s.string(stack.pop())))
                continue
            if name == 'STRINGHASH':
                v = stack.pop()
                t = as_text(v)
                stack.append(i32(joaat(t if t is not None else str(v))))
                continue
            if name == 'TEXT_LABEL_ASSIGN_STRING':
                dst = stack.pop()
                t = as_text(stack.pop())
                dst.set(Str((t or '')[:a[0] - 1]))
                continue
            if name == 'TEXT_LABEL_ASSIGN_INT':
                dst = stack.pop()
                dst.set(Str(str(stack.pop())))
                continue
            if name == 'TEXT_LABEL_APPEND_STRING':
                dst = stack.pop()
                t = as_text(stack.pop()) or ''
                dst.set(Str(((as_text(dst) or '') + t)[:a[0] - 1]))
                continue
            if name == 'TEXT_LABEL_APPEND_INT':
                dst = stack.pop()
                v = stack.pop()
                dst.set(Str(((as_text(dst) or '') + str(v))[:a[0] - 1]))
                continue
            if name == 'TEXT_LABEL_COPY':
                dst = stack.pop()
                size = stack.pop()
                n = stack.pop()
                vals = stack[len(stack) - n:]
                del stack[len(stack) - n:]
                vals = vals[::-1]
                for k in range(min(n, size)):
                    dst.add(k).set(vals[k])
                continue
            raise VMError('opcode not implemented: %s at %X' % (name, x.off))


def dump(src: str, dst: str) -> None:
    s = Script(src)
    with open(dst, 'w', encoding='utf-8') as out:
        out.write('; %s ver=%d table=%s code=%d strings=%d natives=%d statics=%d functions=%d\n' % (
            s.name, s.ver, s.table_name, s.code_size, s.strings_size, s.natives_n, s.statics_n, len(s.functions)))
        fidx = {f.off: f.index for f in s.functions}
        last = None
        for x in s.instrs:
            if x.name == 'ENTER':
                out.write('\n== func_%d @%X (params=%d frame=%d) ==\n' % (fidx[x.off], x.off, x.args[0], x.args[1]))
            if x.name == 'STRING' and last is not None:
                txt = repr(s.string(last))
            elif x.name == 'SWITCH':
                txt = ' '.join('%d:%X' % (v, t) for v, t in x.args[0])
            elif x.name == 'CALL':
                txt = 'func_%s @%X' % (fidx.get(s.resolve(x.args[0]), '?'), x.args[0])
            elif x.name.endswith('JZ') or x.name == 'J':
                txt = '%X' % x.args[0]
            elif x.name == 'NATIVE':
                txt = 'args=%d ret=%d #%d 0x%016X' % (x.args[0], x.args[1], x.args[2], s.natives[x.args[2]])
            elif x.name == 'ENTER':
                txt = '%d %d' % x.args[:2]
            else:
                txt = ' '.join(str(v) for v in x.args)
            out.write('%06X  %-24s %s\n' % (x.off, x.name, txt))
            last = _push_value(x)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    dump(sys.argv[1], sys.argv[2])
