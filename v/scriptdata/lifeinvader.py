"""Lifeinvader data (profiles, walls, friends, texts) computed by running appinternet.ysc.

On www.lifeinvader.com the page only brings the frame; the browser script picks the
profile and fills every slot. Its tables (46 consecutive functions) are pure lookups by
profile / mission id, so they are evaluated here for every profile (0..210), story mission
(0..93) and random-character mission (0..62), and written into the hand-written provider
(providers/www.lifeinvader.com.js, between "// @@DATA" and "// @@END").

Locating the functions: the sidebar function writes "LFI_FAMILY", "LFI_FRIENDS",
"LFI_STALKING" and compares with "LFI_UNKNOWN"; the cluster starts two functions before it
and every member is checked against its expected parameter/return counts (SIGNATURES).

Game state while evaluating (like a story-complete save for the tables that need it):
story missions not counted (the provider decides at run time), random-character missions
done, Michael as the player. The wall order comes from CANON below (a reference save with
the story complete: the usual mission order, random-character missions right after the
mission that unlocks them; chosen branches: jewel store prep A, port heist A, FIB 3A,
big score 2A, ending C).
"""
from __future__ import annotations

import json
import re

try:
    from . import gxt2, ysc
    from .prices import ScriptLayoutError
except ImportError:  # run as a script
    import gxt2  # type: ignore
    import ysc  # type: ignore
    from prices import ScriptLayoutError  # type: ignore

# (params, returns) of the 46 functions of the cluster, in code order
SIGNATURES = [(2, 0), (2, 0), (1, 0), (1, 4), (1, 1), (1, 1), (1, 1), (1, 1), (2, 1), (0, 1), (1, 1), (1, 1),
              (1, 1), (1, 4), (1, 4), (1, 1), (1, 1), (1, 0), (2, 1), (1, 0), (2, 1), (1, 1), (1, 0), (1, 1),
              (1, 1), (2, 1), (2, 1), (3, 0), (2, 4), (1, 1), (2, 1), (2, 1), (2, 1), (1, 1), (1, 1), (0, 1),
              (1, 1), (1, 0), (1, 0), (1, 4), (1, 4), (1, 4), (1, 4), (1, 4), (1, 4), (2, 0)]
# role -> position in the cluster
ROLE = {
    'cnt': 3, 'stalking_n': 4, 'n_stalking': 5, 'stalking_top': 6, 'friends_n': 7, 'rc_flag': 8,
    'friends_top': 11, 'family_n': 12, 'small': 13, 'name': 14, 'family_top': 15, 'page': 16,
    'stalk': 18, 'friend': 20, 'n_friends': 21, 'first_b': 23, 'first_a': 24, 'rc_count': 25,
    'rc_start': 26, 'block': 29, 'author': 30, 'm_count': 31, 'm_start': 32, 'open': 36,
    'med_stalk': 39, 'med_friends': 40, 'med_photos': 41, 'large': 44,
}
NONE = 211

# Story missions (script names, in the game's mission enum order) and random-character missions
STORY = ('armenian1 armenian2 armenian3 Assassin_Valet Assassin_Multi Assassin_Hooker Assassin_Bus '
         'Assassin_Construction carsteal1 carsteal2 carsteal3 carsteal4 chinese1 chinese2 exile1 exile2 exile3 '
         'family1 family2 family3 family4 family5 family6 finale_intro finaleA finaleB finaleC1 finaleC2 '
         'finale_credits fbi1 fbi2 fbi3 fbi4_intro fbi4_prep1 fbi4_prep2 fbi4_prep3 fbi4_prep4 fbi4_prep5 fbi4 '
         'fbi5A franklin0 franklin1 franklin2 lamar1 lester1 martin1 michael1 michael2 michael3 michael4 '
         'me_amanda1 me_jimmy1 me_tracey1 prologue1 drf1 drf2 drf3 drf4 drf5 solomon1 solomon2 solomon3 '
         'trevor1 trevor2 trevor3 trevor4 agency_heist1 agency_heist2 agency_prep1 agency_heist3A '
         'agency_heist3B docks_setup docks_prep1 docks_prep2B docks_heistA docks_heistB finale_heist1 '
         'finale_heist2_intro finale_heist_prepA finale_heist_prepB finale_heist_prepC1 finale_heist_prepC2 '
         'finale_heist_prepC3 finale_heist_prepD finale_heist2A finale_heist2B jewelry_setup1 jewelry_prep1A '
         'jewelry_prep2A jewelry_prep1B jewelry_heist rural_bank_setup rural_bank_prep1 rural_bank_heist').split()
RC = ('Abigail1 Abigail2 Barry1 Barry2 Barry3 Barry3A Barry3C Barry4 Dreyfuss1 Epsilon1 Epsilon2 Epsilon3 '
      'Epsilon4 Epsilon5 Epsilon6 Epsilon7 Epsilon8 Extreme1 Extreme2 Extreme3 Extreme4 Fanatic1 Fanatic2 '
      'Fanatic3 Hao1 Hunting1 Hunting2 Josh1 Josh2 Josh3 Josh4 Maude1 Minute1 Minute2 Minute3 MrsPhilips1 '
      'MrsPhilips2 Nigel1 Nigel1A Nigel1B Nigel1C Nigel1D Nigel2 Nigel3 Omega1 Omega2 Paparazzo1 Paparazzo2 '
      'Paparazzo3 Paparazzo3A Paparazzo3B Paparazzo4 Rampage1 Rampage2 Rampage3 Rampage4 Rampage5 TheLastOne '
      'Tonya1 Tonya2 Tonya3 Tonya4 Tonya5').split()
CANON = '''
prologue1 armenian1 armenian2 Tonya1 armenian3 franklin0 family1 family3 Barry1 Barry2 family2 drf1
lester1 me_amanda1 jewelry_setup1 jewelry_prep1A jewelry_prep2A jewelry_heist Abigail1 Epsilon1 Epsilon2
lamar1 Tonya2 Paparazzo1 Paparazzo2 Hao1 Dreyfuss1
trevor1 MrsPhilips1 Nigel1 Nigel1A Nigel1B Nigel1C Nigel1D Hunting1 Omega1 Minute1 Rampage1 Maude1
chinese1 trevor2 Josh1 Josh2 Josh3 Josh4 chinese2 trevor3 Barry3 Barry3A Barry3C
family4 drf2 fbi1 Extreme1 Fanatic1 fbi2 Nigel2 family5 fbi3 Epsilon3 Fanatic2 franklin1 Assassin_Valet Tonya3
docks_setup docks_prep1 docks_heistA Epsilon4 Extreme2 fbi4_intro fbi4_prep1 fbi4_prep2 fbi4_prep3
fbi4_prep4 fbi4_prep5 fbi4 carsteal1 Paparazzo3 Paparazzo3A carsteal2 solomon1 Assassin_Multi martin1
carsteal3 Epsilon5 Extreme3 exile1 rural_bank_setup rural_bank_prep1 rural_bank_heist exile2 Minute2
exile3 Minute3 Nigel3 Abigail2 Rampage2 Hunting2 fbi5A Assassin_Hooker drf3 Epsilon6 Paparazzo3B
trevor4 finale_heist1 michael1 Fanatic3 carsteal4 michael2 solomon2 Tonya4 agency_heist1 agency_heist2
agency_prep1 agency_heist3A Barry4 Extreme4 family6 Assassin_Bus me_jimmy1 me_tracey1
Epsilon7 solomon3 michael3 Assassin_Construction Rampage3 drf4 franklin2 michael4 Epsilon8 Paparazzo4
Rampage4 Rampage5 Omega2 Tonya5 MrsPhilips2 finale_heist2_intro finale_heist_prepA finale_heist_prepC1
finale_heist_prepC2 finale_heist_prepC3 finale_heist_prepD finale_heist2A finale_intro finaleC1
finaleC2 finale_credits drf5 TheLastOne
'''.split()


def mission_order() -> dict:
    def node(name):
        return 'm%d' % STORY.index(name) if name in STORY else 'r%d' % RC.index(name)
    order = [node(n) for n in CANON]
    assert len(set(order)) == len(order)
    return {'order': order, 'names': list(CANON)}


def locate(s: ysc.Script) -> list:
    """Offsets of the 46 cluster functions."""
    side = [f for f in s.functions
            if {'LFI_FAMILY', 'LFI_FRIENDS', 'LFI_STALKING', 'LFI_UNKNOWN'} <= set(f.strings)]
    if len(side) != 1:
        raise ScriptLayoutError('%s: Lifeinvader sidebar function not found (%d candidates)' % (s.path, len(side)))
    start = side[0].index - 2
    cluster = s.functions[start:start + len(SIGNATURES)]
    got = [(f.nparams, f.nret) for f in cluster]
    if got != SIGNATURES:
        bad = [i for i, (a, b) in enumerate(zip(got, SIGNATURES)) if a != b]
        raise ScriptLayoutError('%s: Lifeinvader functions do not match the expected layout (positions %s)'
                                % (s.path, bad[:8]))
    for pos, need in ((0, 'LFI_M'), (13, 'SMALL_'), (14, 'LFI_'), (39, 'MED_'), (44, 'LARGE_')):
        if need not in cluster[pos].strings:
            raise ScriptLayoutError('%s: Lifeinvader function %d does not use "%s"' % (s.path, pos, need))
    return [f.off for f in cluster]


def _text(v) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    return ysc.as_text(v)


def tables(s: ysc.Script) -> dict:
    """{profile id: entry} like the provider's D.profiles (without texts)."""
    fx = locate(s)
    F = {role: fx[pos] for role, pos in ROLE.items()}
    # mission flag used by the friend counter: its callee outside the cluster with 1 param
    inside = set(fx)
    mission = [c for c in s.func_at(F['friends_n']).calls
               if c not in inside and (s.func_at(c).nparams, s.func_at(c).nret) == (1, 1)]
    vm = ysc.VM(s)
    hooks = {F['rc_flag']: ysc.hook(2)(lambda rc, kind: 1 if kind == 7 else 0)}   # random-character missions done
    for c in set(mission):
        hooks[c] = ysc.hook(1)(lambda m: 0)                                        # story missions: provider decides
    vm.hooks = hooks
    call = vm.call
    strip = lambda t: re.sub(r'^LFI_', '', t)  # noqa: E731

    out = {}
    for p in range(NONE):
        name = _text(call(F['name'], p))
        if name == 'LFI_UNKNOWN':
            continue
        e = {'name': strip(name or '')}
        for key, role in (('small', 'small'), ('large', 'large'), ('medPhotos', 'med_photos'),
                          ('medFriends', 'med_friends'), ('medStalk', 'med_stalk')):
            v = _text(call(F[role], p))
            if v is not None and v != 'BLANK':
                e[key] = v
        if call(F['open'], p):
            e['open'] = 1
        if call(F['page'], p):
            e['page'] = 1
        if e.get('page'):
            e['cnt'] = strip(_text(call(F['cnt'], p)) or '')
        fam, fri, stk = call(F['family_top'], p), call(F['friends_top'], p), call(F['stalking_top'], p)
        fam_n, fri_n, stk_n = call(F['family_n'], p), call(F['friends_n'], p), call(F['stalking_n'], p)
        if fam or fri or stk or fam_n or fri_n != -1 or stk_n:
            e['side'] = [fam, fam_n, fri, fri_n, stk, stk_n]
        nf = call(F['n_friends'], p)
        if nf > 0:
            e['friends'] = [call(F['friend'], p, i) for i in range(1, nf + 1)]
        ns = call(F['n_stalking'], p)
        if ns > 0:
            e['stalking'] = [call(F['stalk'], p, i) for i in range(1, ns + 1)]
        blk = call(F['block'], p)
        if blk:
            e['block'] = blk
            m, r = {}, {}
            for i in range(94):
                st = call(F['m_start'], p, i)
                if st != -1:
                    m[str(i)] = [st, call(F['m_count'], p, i)]
            for i in range(63):
                st = call(F['rc_start'], p, i)
                if st != -1:
                    r[str(i)] = [st, call(F['rc_count'], p, i)]
            if m:
                e['mission'] = m
            if r:
                e['rc'] = r
            a, b = call(F['first_a'], p), call(F['first_b'], p)
            if a != -1 and b >= a:
                e['first'] = [a, b]
            # author of each post: up to the highest index any post uses
            hi = e['first'][1] if 'first' in e else (7 if p == 8 else 0)
            if p == 8:
                hi = max(hi, 7)
            for st, n in list(m.values()) + list(r.values()):
                hi = max(hi, st + n - 1)
            if hi > 0:
                e['author'] = [call(F['author'], p, i) for i in range(hi + 1)]
        out[p] = e
    return out


def texts(profiles: dict, gxt_dir: str, gxt_patch: str | None, strings_global: str) -> dict:
    """Texts the provider needs: G (global.gxt2, by hash) and M / F / T (lfi_m/f/t.gxt2)."""
    blocks = {C: gxt2.read_block('lfi_' + C.lower(), gxt_dir, gxt_patch) for C in 'MFT'}
    with open(strings_global, encoding='utf-8') as fh:
        glob_ = json.load(fh)
    want = set()
    for e in profiles.values():
        for suf in ('', '_OC', '_RP'):
            want.add('LFI_' + e['name'] + suf)
        if e.get('cnt'):
            want.add('LFI_' + e['cnt'])
        if e.get('author'):
            for C in 'MFT':
                for i in range(len(e['author'])):
                    want.add('LFI_%s%s_%d' % (C, e['block'], i))
    out = {'G': {}, 'M': {}, 'F': {}, 'T': {}}
    for label in sorted(want):
        h = ysc.joaat(label)
        k = label[4:] if label.startswith('LFI_') else label
        hit = False
        for C in 'MFT':
            if h in blocks[C]:
                out[C][k] = blocks[C][h]
                hit = True
        if not hit and '%08x' % h in glob_:
            out['G'][k] = glob_['%08x' % h]
    return out


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def data_block(profiles: dict, text: dict, order: dict) -> str:
    """The provider's `const D = {...};` (same layout as the original generator)."""
    lines = ['  const D = {',
             '    // misiones terminadas, de la primera a la última (m = historia, r = personaje aleatorio):',
             '    // %s' % ' '.join(order['names']),
             '    order: %s,' % _compact(order['order']),
             '    // perfil (id del script) -> nombre (label LFI_x), fotos (fotogramas del SWF), open =',
             '    // visible (func_8414), page = empresa (func_8394), side = [familia, n, amigo, n,',
             '    // acosado, n] (func_8393/8390, 8389/8385, 8384/8382), friends / stalking (func_8398,',
             '    // func_8396), block (func_8407), mission / rc = misión -> [primera publicación,',
             '    // cuántas] (func_8410/8409, func_8404/8403), first (func_8402..8401), author',
             '    // (func_8408: perfil que firma cada publicación)',
             '    profiles: {']
    for pid in sorted(profiles, key=int):
        lines.append('      %s: %s,' % (pid, _compact(profiles[pid])))
    lines.append('    },')
    lines.append('    // textos: G = global.gxt2; M / F / T = lfi_m / lfi_f / lfi_t.gxt2 (label sin "LFI_")')
    lines.append('    text: {')
    for blk in ('G', 'M', 'F', 'T'):
        lines.append('      %s: {' % blk)
        for k in sorted(text[blk]):
            lines.append('        %s: %s,' % (_compact(k), _compact(text[blk][k])))
        lines.append('      },')
    lines.append('    },')
    lines.append('  };')
    return '\n'.join(lines)


def write_provider(template: str, dst: str, block: str) -> int:
    with open(template, encoding='utf-8') as fh:
        src = fh.read()
    pat = re.compile(r'(  // @@DATA[^\n]*\n).*?(\n  // @@END)', re.S)
    if not pat.search(src):
        raise ScriptLayoutError('%s: no "// @@DATA ... // @@END" block' % template)
    src = pat.sub(lambda m: m.group(1) + block + m.group(2), src, count=1)
    with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(src)
    return len(src.encode('utf-8'))


def build(script: ysc.Script, gxt_dir: str, gxt_patch: str | None, strings_global: str,
          template: str, dst: str, log=print) -> dict:
    profiles = tables(script)
    text = texts(profiles, gxt_dir, gxt_patch, strings_global)
    order = mission_order()
    n = write_provider(template, dst, data_block(profiles, text, order))
    log('  lifeinvader: %d profiles, texts %s, %d bytes -> %s' % (
        len(profiles), ' '.join('%s:%d' % (k, len(v)) for k, v in text.items()), n, dst))
    return {'profiles': profiles, 'text': text, 'order': order}
