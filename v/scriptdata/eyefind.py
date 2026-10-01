"""eyefind.info news and bleeter.biz pages, read from appinternet.ysc.

news     The news function (located by the labels it writes, "NWS_PRO_HL"/"NWS_PRO_S", and its
         3 params / 1 return) picks, for the story event stored in a global, a headline label
         ("NWS_<x>_HL"), a story label ("NWS_<x>_S") and a range of variants [lo, hi]; the
         newspaper of each (event, variant) comes from the function it calls with 2 params.
         The event table is read statically from the bytecode (for each "event == n" branch,
         the first constant stored in the two range locals and the first labels copied into
         the two output buffers), and the newspaper is computed by running that function.
         Output: [{event, hl, s, variants: [[k, paper], ...]}, ...]

bleeter  The function right after the one that builds "BLE_<n>" labels fills three static
         arrays: first bleet, last bleet and mission of each group of bleets. They are read
         statically (first constant stored at each index, i.e. the story-complete branch).
         The page order is the most recent mission first, each mission once.
         Output: {groups: [[first, last], ...], mission: [...], order: [...]}
"""
from __future__ import annotations

import collections
import re

try:
    from . import ysc
    from .prices import ScriptLayoutError, expect, uniq
except ImportError:  # run as a script
    import ysc  # type: ignore
    from prices import ScriptLayoutError, expect, uniq  # type: ignore

_LABEL = re.compile(r'^[A-Z0-9_]+$')


def _find(s: ysc.Script, strings: set, sig: tuple, what: str) -> ysc.Function:
    c = [f for f in s.functions if strings <= set(f.strings) and (f.nparams, f.nret) == sig]
    if len(c) != 1:
        raise ScriptLayoutError('%s: %s not found (%d candidates)' % (s.path, what, len(c)))
    return c[0]


# ---- news --------------------------------------------------------------------------------
def news(s: ysc.Script) -> list:
    fn = _find(s, {'NWS_PRO_HL', 'NWS_PRO_S'}, (3, 1), 'news function')
    papers = [c for c in uniq(fn.calls) if (s.func_at(c).nparams, s.func_at(c).nret) == (2, 1)]
    if len(papers) != 1:
        raise ScriptLayoutError('%s: newspaper function not found (%d candidates)' % (s.path, len(papers)))
    body = s.body(fn)
    # the event local: the one compared with constants the most ("if (event == n)")
    cmp = collections.Counter()
    for a, b, c in zip(body, body[1:], body[2:]):
        if a.name == 'LOCAL_U8_LOAD' and ysc._push_value(b) is not None and c.name == 'IEQ_JZ':
            cmp[a.args[0]] += 1
    if not cmp:
        raise ScriptLayoutError('%s: news function has no event branches' % s.path)
    ev = cmp.most_common(1)[0][0]
    lo_local, hi_local = ev + 1, ev + 2          # declared right after the event local
    events = {}
    cur = None
    last_push = None
    last_str = None
    for i, x in enumerate(body):
        if (x.name == 'LOCAL_U8_LOAD' and x.args[0] == ev and i + 2 < len(body)
                and ysc._push_value(body[i + 1]) is not None and body[i + 2].name == 'IEQ_JZ'):
            n = ysc._push_value(body[i + 1])
            cur = {'n': n, 'lo': None, 'hi': None, 'hl': None, 's': None}
            events[n] = cur
        elif cur is not None:
            if x.name == 'LOCAL_U8_STORE' and last_push is not None and last_push >= 0:
                if x.args[0] == lo_local and cur['lo'] is None:
                    cur['lo'] = last_push
                elif x.args[0] == hi_local and cur['hi'] is None:
                    cur['hi'] = last_push
            elif x.name == 'TEXT_LABEL_ASSIGN_STRING' and last_str and i >= 1 and body[i - 1].name == 'LOCAL_U8_LOAD':
                dst = body[i - 1].args[0]
                if dst == 0 and cur['hl'] is None:
                    cur['hl'] = last_str
                elif dst == 1 and cur['s'] is None:
                    cur['s'] = last_str
        if x.name == 'STRING':
            t = s.string(last_push) if last_push is not None else None
            last_str = t if t and _LABEL.match(t) else None
        elif x.name != 'LOCAL_U8_LOAD':
            last_str = None if x.name != 'TEXT_LABEL_ASSIGN_STRING' else last_str
        last_push = ysc._push_value(x)
    vm = ysc.VM(s)
    out = []
    for n in sorted(events):
        e = events[n]
        if not e['hl'] or e['lo'] is None or e['hi'] is None:
            continue
        variants = [[v, vm.call(papers[0], n, v)] for v in range(e['lo'], e['hi'] + 1)]
        out.append({'event': n, 'hl': e['hl'], 's': e['s'], 'variants': variants})
    return out


# ---- bleeter -----------------------------------------------------------------------------
def _static_array_stores(s: ysc.Script, fn: ysc.Function) -> list:
    """[(static, index, value)] for 'static[index] = constant' in code order."""
    out = []
    st: list = []
    for x in s.body(fn):
        v = ysc._push_value(x)
        if v is not None:
            if x.name == 'PUSH_U8_U8' or x.name == 'PUSH_U8_U8_U8':
                st.extend(x.args)
            else:
                st.append(v)
            continue
        if x.name in ('IADD', 'ISUB', 'IMUL') and len(st) >= 2 and all(isinstance(q, int) for q in st[-2:]):
            b, a = st.pop(), st.pop()
            st.append(a + b if x.name == 'IADD' else a - b if x.name == 'ISUB' else a * b)
            continue
        if x.name in ('STATIC_U8', 'STATIC_U16', 'STATIC_U24'):
            st.append(('S', x.args[0]))
            continue
        if x.name in ('ARRAY_U8_STORE', 'ARRAY_U16_STORE') and len(st) >= 3:
            base, idx, val = st[-1], st[-2], st[-3]
            if isinstance(base, tuple) and isinstance(idx, int) and isinstance(val, int):
                out.append((base[1], idx, val))
        st = []
    return out


def bleeter(s: ysc.Script) -> dict:
    lab = _find(s, {'BLE_', 'BLE_BLANK'}, (1, 4), 'bleet label function')
    fn = s.functions[lab.index + 1]
    stores = _static_array_stores(s, fn) if (fn.nparams, fn.nret) == (1, 0) else []
    count = collections.Counter(a for a, _, _ in stores)
    arrays = [a for a in uniq(a for a, _, _ in stores) if count[a] >= 10][:3]
    if len(arrays) != 3:
        raise ScriptLayoutError('%s: bleeter group function not found after %X' % (s.path, lab.off))
    first = {a: {} for a in arrays}
    for a, i, v in stores:
        if a in first:
            first[a].setdefault(i, v)
    start, end, mission = (first[a] for a in arrays)
    if min(len(start), len(end), len(mission)) < 10:
        raise ScriptLayoutError('%s: bleeter group tables look wrong' % s.path)
    groups = [[start[g], end[g]] for g in sorted(start)]
    # Page order with the story complete: the most recent mission first; alternative
    # groups of one mission (same range of bleets) only once.
    order, seen_missions, seen_ranges = [], set(), set()
    for g in sorted(start, reverse=True):
        rng = (start[g], end[g])
        first_for_mission = min(x for x in mission if mission[x] == mission[g])
        if mission[g] in seen_missions or rng in seen_ranges:
            continue
        seen_missions.add(mission[g])
        seen_ranges.add((start[first_for_mission], end[first_for_mission]))
        order.append(first_for_mission)
    return {'groups': groups, 'mission': [mission[g] for g in sorted(mission)], 'order': order}
