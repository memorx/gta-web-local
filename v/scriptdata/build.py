#!/usr/bin/env python3
"""Compute, from the user's own game scripts, the data the browser script puts into the websites.

Writes into --out:
    host_data.json            vehiclePrices (story mode, current sites), news (eyefind),
                              bleeter (bleeter.biz pages), vehiclePrices2013 (2013 sites)
    vehicle_sites_2013.json   the 2013 vehicle sites' own id tables (from their ActionScript)
    www.lifeinvader.com.js    the Lifeinvader provider: the template with its data block filled
    script_strings.json       every string the current appinternet script pushes (label names;
                              the text stage uses it to know which GXT labels the script needs)

Inputs (all extracted from the user's game):
    --ysc              current appinternet.ysc (Enhanced: update2.rpf, Legacy: update.rpf;
                       x64/levels/gta5/script/script_rel.rpf)
    --ysc-2013         base appinternet.ysc (x64b.rpf levels/gta5/script/script_rel.rpf)
    --as-2013          JPEXS "-export script" folder of the 2013 vehicle sites (x64b.rpf
                       scaleform_web.rpf .gfx files): <dir>/<any>/scripts/__Packages/...
                       (or --vehicle-tables with an existing vehicle_sites_2013.json)
    --gxt / --gxt-patch  american_rel folder with lfi_m/lfi_f/lfi_t.gxt2 (+ patch folder)
    --strings-global   the {hash: text} table of global.gxt2 built by the text stage
    --provider-template  providers/www.lifeinvader.com.js (data block empty)

Usage:
    python build.py --ysc A --ysc-2013 B --as-2013 DIR --gxt DIR [--gxt-patch DIR]
                    --strings-global FILE --provider-template FILE --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'scriptdata'

from scriptdata import eyefind, lifeinvader, prices, ysc  # noqa: E402

SOURCE = 'computed from appinternet.ysc of the local game install (v/scriptdata)'


def _dump(obj, path: str) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(obj, fh, indent=1)
    os.replace(tmp, path)


def build(ysc_path: str, ysc_2013: str, out: str, gxt: str, strings_global: str, provider_template: str,
          as_2013: str | None = None, vehicle_tables: str | None = None, gxt_patch: str | None = None,
          log=print) -> dict:
    """Run every port and write the four files into `out`. Returns their paths."""
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    s = ysc.Script(ysc_path)
    log('scriptdata: %s (RSC7 v%d, %s opcode table, %d functions)' % (
        os.path.basename(ysc_path), s.ver, s.table_name, len(s.functions)))
    if vehicle_tables:
        with open(vehicle_tables, encoding='utf-8') as fh:
            tables = json.load(fh)
    elif as_2013:
        tables = prices.site_tables_2013(as_2013)
    else:
        raise ValueError('need as_2013 or vehicle_tables')
    tables_path = os.path.join(out, 'vehicle_sites_2013.json')
    _dump(tables, tables_path)
    cur = prices.current_prices(s, log=log)
    data = {
        'source': SOURCE,
        'vehiclePrices': dict(sorted(cur.items())),
        'news': eyefind.news(s),
        'bleeter': eyefind.bleeter(s),
        'vehiclePrices2013': prices.prices_2013(ysc_2013, tables, log=log),
    }
    log('  news: %d events | bleeter: %d groups, %d pages' % (
        len(data['news']), len(data['bleeter']['groups']), len(data['bleeter']['order'])))
    host_path = os.path.join(out, 'host_data.json')
    _dump(data, host_path)
    provider = os.path.join(out, 'www.lifeinvader.com.js')
    lifeinvader.build(s, gxt, gxt_patch, strings_global, provider_template, provider, log=log)
    strings_path = os.path.join(out, 'script_strings.json')
    _dump(sorted({t for f in s.functions for t in f.strings}), strings_path)
    log('scriptdata: done in %.0f s -> %s' % (time.time() - t0, out))
    return {'host_data': host_path, 'vehicle_sites_2013': tables_path, 'lifeinvader': provider,
            'script_strings': strings_path}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Compute the websites\' script data from the local game scripts.')
    ap.add_argument('--ysc', required=True, help='current appinternet.ysc')
    ap.add_argument('--ysc-2013', required=True, help='base (x64b.rpf) appinternet.ysc')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--as-2013', help='JPEXS ActionScript export of the 2013 sites')
    g.add_argument('--vehicle-tables', help='existing vehicle_sites_2013.json instead of --as-2013')
    ap.add_argument('--gxt', required=True, help='american_rel folder (lfi_m/f/t.gxt2)')
    ap.add_argument('--gxt-patch', help='patch american_rel folder (optional)')
    ap.add_argument('--strings-global', required=True, help='{hash: text} JSON of global.gxt2')
    ap.add_argument('--provider-template', required=True, help='providers/www.lifeinvader.com.js')
    ap.add_argument('--out', required=True, help='output folder')
    a = ap.parse_args(argv)
    try:
        build(a.ysc, a.ysc_2013, a.out, a.gxt, a.strings_global, a.provider_template,
              as_2013=a.as_2013, vehicle_tables=a.vehicle_tables, gxt_patch=a.gxt_patch)
    except (prices.ScriptLayoutError, ysc.VMError, ValueError, OSError) as e:
        print('scriptdata: ERROR: %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
