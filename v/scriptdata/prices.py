"""Story-mode prices of the six vehicle websites, computed by running appinternet.ysc.

In the game, opening legendarymotorsport.net & co. makes the browser script send
SET_PRICES(id, price) for every vehicle; without it the site shows none. This module runs
the user's own script in the VM (ysc.py) and records those calls.

Current script (update2.rpf / update.rpf):
    The story-mode price loop is located by signature: among the functions that push
    "SET_PRICES", "UPDATE_TEXT" and "ITEM_FREE", the dispatcher calls the Online loop in
    the "if" branch and the story-mode loop in the "else" branch (the last one it calls).
    The loop's callees, in order of first call, are: listed(site, i), vehicle(site, id),
    a flag, price(vehicle, site, flag, mode) and frogger(15, 2). The price function's
    callees are: mission-flag, model(vehicle), special-content, special-subflag,
    catalogue-price, model-price, ... The whole loop runs unmodified except for these
    assumptions (the same ones the site notes document):
      * story complete: every mission flag is set (except the "none" values 94 / -1);
      * special content (returning-player vehicles) available, priced with the story-mode
        model price (not the Online catalogue); collector's edition bonus cars not free;
      * Frogger unlocked; no network game;
      * model price = the base price each vehicle lists first in the model-price switch
        (listed_model_prices): the later adjustments depend on Online unlock state and
        server tunables that do not exist offline.
    Output per site: {id: price | "ITEM_FREE" | 0 (out of stock)}; hidden vehicles
    (price -1) are left out.

2013 script (x64b.rpf, the one the 2013 versions of the sites were made for):
    Same idea, with the functions at fixed offsets (the base archive is the same for every
    copy of the game; the offsets are validated before use). The 2013 sites use their own
    id tables (vehicleData VEHICLE/PAGEID, P&M carNames), so every row is matched by
    vehicle name, and rows without a price get -1 (SSASA defaults to "$71" otherwise).
    No special content (what the sites sold in 2013).
"""
from __future__ import annotations

import glob
import json
import os
import re

try:
    from . import ysc
except ImportError:  # run as a script
    import ysc  # type: ignore

SITES = {10: 'WWW_LEGENDARYMOTORSPORT_NET', 11: 'WWW_ELITASTRAVEL_COM',
         12: 'WWW_WARSTOCK_D_CACHE_D_AND_D_CARRY_COM', 13: 'WWW_DOCKTEASE_COM',
         15: 'WWW_PANDMCYCLES_COM', 16: 'WWW_SOUTHERNSANANDREASSUPERAUTOS_COM'}


class ScriptLayoutError(RuntimeError):
    pass


def uniq(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def expect(s: ysc.Script, off: int, nparams: int, nret: int, what: str) -> ysc.Function:
    f = s.func_at(off)
    if (f.nparams, f.nret) != (nparams, nret):
        raise ScriptLayoutError('%s: %s at %X has %d params / %d returns, expected %d / %d' % (
            s.path, what, f.off, f.nparams, f.nret, nparams, nret))
    return f


# ---- current script ---------------------------------------------------------------------
def locate_current(s: ysc.Script) -> dict:
    loops = {f.off for f in s.functions
             if {'SET_PRICES', 'UPDATE_TEXT', 'ITEM_FREE'} <= set(f.strings)}
    disp = [f for f in s.functions if len([c for c in uniq(f.calls) if c in loops]) >= 2]
    if len(disp) != 1:
        raise ScriptLayoutError('%s: SET_PRICES dispatcher not found (%d candidates)' % (s.path, len(disp)))
    sp = [c for c in uniq(disp[0].calls) if c in loops][-1]
    loop = expect(s, sp, 2, 0, 'story-mode SET_PRICES loop')
    c = uniq(loop.calls)
    if len(c) < 5:
        raise ScriptLayoutError('%s: SET_PRICES loop calls %d functions, expected >= 5' % (s.path, len(c)))
    fx = {'loop': loop.off}
    for name, off, sig in zip(('listed', 'vehicle', 'flag', 'price', 'frogger'), c,
                              ((2, 1), (2, 1), (3, 1), (4, 1), (2, 1))):
        fx[name] = expect(s, off, sig[0], sig[1], name).off
    p = uniq(s.func_at(fx['price']).calls)
    if len(p) < 7:
        raise ScriptLayoutError('%s: price function calls %d functions, expected >= 7' % (s.path, len(p)))
    for name, off, sig in zip(('mission', 'model', 'special', 'special2', 'catalogue', 'model_price', 'bonus'), p,
                              ((1, 1), (2, 1), (0, 1), (2, 1), (3, 1), (4, 1), (0, 1))):
        fx[name] = expect(s, off, sig[0], sig[1], name).off
    return fx


_COND_OPS = {'LOCAL_U8_LOAD', 'PUSH_0', 'PUSH_1', 'PUSH_2', 'PUSH_3', 'PUSH_M1', 'PUSH_U8', 'IEQ', 'INE',
             'IOR', 'IAND', 'INOT', 'GLOBAL_U16_LOAD', 'GLOBAL_U24_LOAD', 'IOFFSET_S16_LOAD',
             'IOFFSET_U8_LOAD', 'GLOBAL_U24', 'GLOBAL_U16', 'IGE', 'ILE', 'IGT', 'ILT'}


def listed_model_prices(s: ysc.Script, fn: ysc.Function) -> dict:
    """{model hash (int32): price} read from the model-price function's switches on the model.

    For every case of every "switch (model)" the price is the first constant stored in the
    price local, skipping the blocks guarded by the network-game local (Online prices and
    tunables). That is the price the case lists first: the base story-mode price before
    the adjustments that depend on Online unlocks and server tunables (trade discount,
    buy-it-now mark-up, convertible variant), which cannot be known offline. Cases whose
    price is only an expression (no constant) are left out, so those vehicles stay hidden.
    """
    body = s.body(fn)
    if len(body) < 3 or body[1].name != 'NATIVE' or body[1].args[0] != 0 or body[2].name != 'LOCAL_U8_STORE':
        raise ScriptLayoutError('%s: model-price function at %X does not start as expected' % (s.path, fn.off))
    net_local = body[2].args[0]            # "network game in progress"
    price_local = net_local + 1            # declared right after it
    pos = {x.off: i for i, x in enumerate(body)}

    def net_block(i):
        """Index to resume at if body[i] starts an "if (network game ...)" condition."""
        y = body[i]
        if y.name != 'LOCAL_U8_LOAD' or y.args[0] != net_local:
            return None
        j = i + 1
        while j < len(body) and j - i < 16:
            z = body[j]
            if z.name == 'JZ':
                k = pos.get(z.args[0])
                if k is None or k <= j:
                    return None
                if k - i < 16 and body[k].name == 'JZ':
                    j += 1                  # short-circuit || / && jumping to the final test
                    continue
                return k
            if z.name not in _COND_OPS and z.name != 'DUP':
                return None
            j += 1
        return None

    online = []                                # index ranges only run in a network game
    for i in range(len(body)):
        e = net_block(i)
        if e is not None:
            online.append((i, e))
    out: dict = {}
    for k, x in enumerate(body):
        if x.name != 'SWITCH' or k == 0 or body[k - 1].name != 'LOCAL_U8_LOAD' or body[k - 1].args[0] != 1:
            continue
        if any(a <= k < b for a, b in online):
            continue                           # a model switch inside an Online-only block
        cases = x.args[0]
        starts = sorted({t for _, t in cases})
        for value, t in cases:
            key = ysc.i32(value)
            if key in out or t not in pos:
                continue
            nxt = next((q for q in starts if q > t), None)
            i = pos[t]
            price = None
            while i < len(body):
                y = body[i]
                if nxt is not None and y.off >= nxt:
                    break
                if y.name == 'J' and (y.args[0] < t or (nxt is not None and y.args[0] >= nxt)):
                    break                                   # "break": leaves the case
                e = net_block(i)
                if e is not None:
                    i = e                                   # skip the network-game block
                    continue
                if y.name == 'LOCAL_U8_STORE' and y.args[0] == price_local:
                    v = ysc._push_value(body[i - 1])
                    if v is not None and v >= 0:
                        price = v
                        break
                i += 1
            if price is not None:
                out[key] = price
    if len(out) < 50:
        raise ScriptLayoutError('%s: only %d model prices found at %X' % (s.path, len(out), fn.off))
    return out


def current_prices(s: ysc.Script, log=print) -> dict:
    fx = locate_current(s)
    table = listed_model_prices(s, s.func_at(fx['model_price']))
    records: list = []

    def on_native(idx, args, nret):
        # BEGIN_SCALEFORM_MOVIE_METHOD(movie, "SET_PRICES") starts a call; the one-argument
        # natives without a result that follow add its parameters (int or text label)
        texts = [ysc.as_text(a) for a in args]
        if 'SET_PRICES' in texts or 'UPDATE_TEXT' in texts:
            records.append([t for t in texts if t in ('SET_PRICES', 'UPDATE_TEXT')][:1])
            return 1
        if nret == 0 and len(args) == 1 and records:
            t = ysc.as_text(args[0])
            records[-1].append(t if t is not None else args[0])
            return None
        return 0

    @ysc.hook(1)
    def mission(flag):
        return 0 if flag in (94, -1) else 1          # story complete

    @ysc.hook(0)
    def special():
        return 1                                      # special content available

    @ysc.hook(2)
    def special2(a, b):
        return 1

    @ysc.hook(2)
    def frogger(a, b):
        return 1                                      # Frogger unlocked

    @ysc.hook(0)
    def bonus():
        return 0                                      # collector's edition bonus: not free

    @ysc.hook(4)
    def model_price(ptr, model, flag, mode):
        if model not in table:
            return 0
        ptr.set(table[model])
        return 1

    @ysc.hook(3)
    def catalogue(model, a, b):
        return table.get(model, -1)                   # special content: story-mode price

    vm = ysc.VM(s, on_native=on_native)
    vm.hooks = {fx['mission']: mission, fx['special']: special, fx['special2']: special2,
                fx['frogger']: frogger, fx['model_price']: model_price, fx['catalogue']: catalogue,
                fx['bonus']: bonus}
    pf = s.func_at(fx['price'])
    vm.bit_override = [(pf.off, pf.end, 1)]   # the special-content flag tested in the price function
    out = {}
    for site_id, site in SITES.items():
        records.clear()
        vm.call(fx['loop'], ysc.Ptr([0], 0), site_id)
        prices = {}
        for r in records:
            if r[:1] != ['SET_PRICES'] or len(r) < 3:
                continue
            vid, price = r[1], r[2]
            if price == -1:
                continue                               # hidden
            prices[str(vid)] = price
        out[site] = dict(sorted(prices.items()))
        log('  %s: %d prices' % (site, len(prices)))
    return out


# ---- 2013 script (x64b.rpf) --------------------------------------------------------------
# Offsets in the base appinternet.ysc; validated by check_2013 before use.
F13_LOOP = 0x3742F       # SET_PRICES loop
F13_LISTED = 0x361F0     # listed(site, i)
F13_ENUM = 0x36A68       # vehicle(site, id)
F13_PRICE = 0x35D7B      # price(vehicle)
F13_MODEL = 0x2E38D      # vehicle -> joaat(model)
F13_MISSION = 0x5489     # mission flag
F13_SPECIAL = 0x2B355    # special content
F13_SPECIAL2 = 0x361CD   # special content sub-flag
F13_FROGGER = 0x35C2B    # Frogger unlock
N13_IS_BIT_SET = 0xA921AA820C25702F
N13_IS_MODEL_A_VEHICLE = 0x19AAC8F07BFEC53E
N13_FLOOR = 0xF34EE736CF047844
N13_NETWORK_IS_GAME_IN_PROGRESS = 0x10FAB35428CCC9D7

# Model names appinternet uses (to name the hash the 2013 model function returns)
MODELS = '''adder airbus akuma alpha annihilator asea asterope baller2 banshee barracks bati bati2 besra bfinjection
bifta bison blade blazer blazer3 blista2 bmx bobcatxl bodhi2 btype buffalo buffalo2 buffalo3 bullet bus buzzard
carbonizzare carbonrs cargobob cavalcade cavalcade2 cheetah coach cogcabrio comet2 coquette coquette2 crusader
cruiser cuban800 dilettante dodo dominator dominator2 double dubsta3 dukes dump dune duster elegy2 entityxf
exemplar f620 faggio2 felon felon2 feltzer2 frogger fugitive furoregt fusilade gauntlet gauntlet2 glendale
granger hakuchou hexer hotknife huntley infernus ingot innovation intruder issi2 jb700 jester jetmax journey
kalahari khamelion luxor mammatus marquis marshall massacro maverick miljet minivan monroe monster mule ninef
ninef2 oracle2 panto paradise pcj penumbra picador pigalle premier primo radi rancherxl rapidgt rapidgt2
ratloader rebel rebel2 regina rentalbus rhapsody rhino rocoto ruffian sadler sanchez sanchez2 sandking
sandking2 schwarzer scorcher seashark sentinel sentinel2 shamal sovereign speeder squalo stalion stalion2
stanier stinger stingergt stratum stretch stunt submersible2 suntrap superd surano surfer swift tailgater
thrust titan tribike tribike2 tribike3 tropic turismor vacca vader velum vestra vigero voltic warrener
washington youga zentorno zion zion2 ztype'''.split()


def check_2013(s: ysc.Script) -> None:
    try:
        loop = s.func_at(F13_LOOP)
    except KeyError:
        raise ScriptLayoutError('%s: no function at %X (not the base appinternet.ysc?)' % (s.path, F13_LOOP))
    need = {F13_LISTED, F13_ENUM, F13_PRICE, F13_FROGGER}
    if 'SET_PRICES' not in loop.strings or not need <= set(loop.calls):
        raise ScriptLayoutError('%s: function %X is not the expected SET_PRICES loop' % (s.path, F13_LOOP))


def loop_bounds_2013(s: ysc.Script) -> dict:
    """Vehicles per site, read from the loop code (LOCAL 1 == site -> LOCAL 6 = N; else 9)."""
    out, seq = {}, []
    for x in s.body(s.func_at(F13_LOOP)):
        if x.name == 'LEAVE':
            break
        if x.name == 'PUSH_U8':
            seq.append(x.args[0])
        elif x.name == 'LOCAL_U8_STORE' and x.args[0] == 6 and seq:
            out[seq[-2] if len(seq) >= 2 else None] = seq[-1]
            seq = []
        elif x.name not in ('IEQ_JZ', 'LOCAL_U8_LOAD', 'J'):
            seq = []
    return out


def script_rows_2013(s: ysc.Script) -> dict:
    """What the base script sends to each site: {site: [[id, vehicle, model, price], ...]}."""
    check_2013(s)
    names = {ysc.joaat(n): n for n in MODELS}

    @ysc.hook(1)
    def mission(flag):
        return 0 if flag in (94, -1) else 1

    @ysc.hook(0)
    def special():
        return 0

    @ysc.hook(2)
    def special2(a, b):
        return 0

    @ysc.hook(2)
    def frogger(a, b):
        return 1

    vm = ysc.VM(s, hooks={F13_MISSION: mission, F13_SPECIAL: special, F13_SPECIAL2: special2, F13_FROGGER: frogger},
                natives={N13_IS_BIT_SET: lambda v, b: (int(v) >> int(b)) & 1, N13_IS_MODEL_A_VEHICLE: 1,
                         N13_FLOOR: lambda f: int(f // 1), N13_NETWORK_IS_GAME_IN_PROGRESS: 0})
    bounds = loop_bounds_2013(s)
    out = {}
    for web, site in SITES.items():
        rows = []
        for i in range(bounds.get(web, bounds.get(None, 9))):
            if not vm.call(F13_LISTED, web, i):
                continue
            vid = i + 3
            enum = vm.call(F13_ENUM, web, vid)
            if enum == -1:
                continue
            price = vm.call(F13_PRICE, enum)
            model = vm.call(F13_MODEL, enum) & 0xFFFFFFFF
            # like the loop: -2 -> 0 (out of stock), 0 -> "ITEM_FREE", the rest as is
            sent = 0 if price == -2 else ('ITEM_FREE' if price == 0 else price)
            rows.append([vid, enum, names.get(model, '0x%08X' % model), sent])
        out[site] = rows
    return out


# ---- 2013 site tables (JPEXS ActionScript export) -----------------------------------------
def parse_site(path: str) -> dict:
    with open(path, encoding='utf-8', errors='replace') as fh:
        src = fh.read()
    src = re.sub(r'\n\s*(?=[.,)\]])', '', src)            # JPEXS wraps long lines
    rows = []
    for m in re.finditer(r'this\.vehicleData\.push\((undefined|\{[^}]*\})\);', src):
        t = m.group(1)
        if t == 'undefined':
            continue
        v = re.search(r'VEHICLE:"([^"]*)"', t)
        p = re.search(r'PAGEID:(\d+)', t)
        d = re.search(r'PRICE:(-?\d+)', t)
        rows.append({'vehicle': v.group(1), 'id': int(p.group(1)), 'default': int(d.group(1)) if d else -1})
    m = re.search(r'this\.carNames = \[([^\]]*)\]', src)
    if not rows and m:                                   # P&M: carNames + prices[id - 3]
        names = re.findall(r'"([^"]*)"', m.group(1))
        rows = [{'vehicle': n, 'id': i + 3, 'default': -1} for i, n in enumerate(names)]
    disp = None
    m = re.search(r'if\(this\.isMP == false\)\s*\{\s*this\.displayArray = \[([^\]]*)\]', src) \
        or re.search(r'this\.displayArray = \[([^\]]*)\]', src)
    if m:
        disp = [int(x) for x in m.group(1).split(',') if x.strip()]
    return {'rows': rows, 'displaySP': disp}


def site_tables_2013(as_dir: str) -> dict:
    """{site: {rows, displaySP}} from <as_dir>/<anything>/scripts/__Packages/.../WWW_*.as"""
    out = {}
    pattern = os.path.join(as_dir, '*', 'scripts', '__Packages', 'com', 'rockstargames', 'gtav', 'web', 'WWW_*.as')
    for f in sorted(glob.glob(pattern)):
        site = os.path.basename(f)[:-3]
        if site in SITES.values():
            out[site] = parse_site(f)
    missing = sorted(set(SITES.values()) - set(out))
    if missing:
        raise ScriptLayoutError('%s: no ActionScript for %s' % (as_dir, ', '.join(missing)))
    return {'source': 'ActionScript of the 2013 websites (x64b.rpf), exported with JPEXS', 'sites': out}


def same_vehicle(label: str, model: str) -> bool:
    """Site VEHICLE label (<= 8 letters: COGCABRI, CAVCADE, SUB2...) ~ script model name
    (cogcabrio, cavalcade, submersible2...): same first letter and one is a subsequence."""
    a, b = label.lower(), model.lower()
    if not a or not b or a[0] != b[0]:
        return False

    def sub(x, y):
        it = iter(y)
        return all(ch in it for ch in x)
    return sub(a, b) or sub(b, a)


def match_2013(tables: dict, srows: dict) -> dict:
    prices = {}
    for site, t in tables.items():
        rows = srows.get(site, [])
        by_id = {r[0]: r for r in rows}
        table = {}
        for row in t['rows']:
            lab, pid = row['vehicle'], row['id']
            r = by_id.get(pid)
            if not (r and same_vehicle(lab, r[2])):
                cand = [x for x in rows if same_vehicle(lab, x[2])]
                cand.sort(key=lambda x: (len(x[2]), x[0]))     # exact model first (stalion, not stalion2)
                r = cand[0] if cand else None
            table[str(pid)] = r[3] if r else -1
        prices[site] = table
    return prices


def prices_2013(ysc_2013: str, tables: dict, log=print) -> dict:
    s = ysc.Script(ysc_2013)
    prices = match_2013(tables['sites'], script_rows_2013(s))
    for site, t in prices.items():
        log('  %s (2013): %d rows, %d with a price' % (site, len(t), sum(1 for v in t.values() if v != -1)))
    return prices
