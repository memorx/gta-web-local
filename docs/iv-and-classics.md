# GTA IV and the classic sites (III, Vice City, San Andreas)

This page explains how `build.py` makes the GTA IV in-game internet and the GTA III /
Vice City / San Andreas websites, what it downloads, how long it takes, and how to check
that your build is the same as everybody else's. GTA V has its own page:
[gta-v.md](gta-v.md).

Nothing from the games and nothing downloaded from the Internet Archive is part of this
repository. GTA IV is converted from **your own copy of the game**; the classic sites are
downloaded by **your own computer** from the Internet Archive's Wayback Machine.

## Quick start

```sh
git clone --recurse-submodules <repository URL> gta-web-local
cd gta-web-local
cp config.example.toml config.toml        # (copy on Windows) then edit the paths in it
python build.py iv                        # GTA IV, TLAD and TBoGT (a few minutes)
python build.py classic                   # III, VC and SA sites (about 2 hours the first time)
python serve.py                           # http://127.0.0.1:8044/
```

If you cloned without `--recurse-submodules`, run `git submodule update --init` once
(see [third_party/README.md](../third_party/README.md)).

`python build.py` (or `python build.py all`) builds every part whose game folder is set
in `config.toml`; the classic sites need no game.

## Requirements

| What | Needed for | Notes |
|---|---|---|
| Python 3.11 or newer | everything | standard library only |
| Git | the `third_party/gtaweb` submodule | |
| Go | GTA IV (building the converter) | optional: when `go` is not on PATH, Go 1.27.1 is downloaded from `go.dev` (SHA-256 checked) into `<work>/tools/go` |
| Internet access | GTA IV (first build only: Go and its modules), classic sites | see [External services](#external-services) |
| A GTA IV install | GTA IV | tested with the Complete Edition (base game and both episodes); without the episodes only the base game is built |
| Node.js 22.12+ and Chrome, Chromium or Edge | `tests/probe.mjs` only | `npm install` in the repository root installs puppeteer-core |
| Pillow | `tests/sheets.py` only | `pip install -r requirements.txt` |

Disk space: about 100 MB for the GTA IV output, 750 MB for the classic sites (375 MB of
downloads kept in `work/` plus 375 MB served from `out/`), 30 MB for Ruffle and about
400 MB for Go and its build cache in `work/tools/` (only when Go is downloaded).

## config.toml

```toml
[paths]
gta4 = "C:/Program Files (x86)/Steam/steamapps/common/Grand Theft Auto IV/GTAIV"
out  = "out"     # what the server shows
work = "work"    # downloads, caches and tools; can be deleted
```

`gta4` is the folder that contains `GTAIV.exe` and `pc/`. Relative paths are resolved
against the folder of the config file. Every script takes `--config <file>` to use
another file. The game folders are only read: the build refuses an `out` or `work`
folder inside a game folder.

## GTA IV

```sh
python build.py iv                     # or: python iv/build_iv.py [--only GTAIV,TLAD,TBoGT]
```

What it does, for the base game and for each episode that is installed:

1. Reads the page texts from `common/text/american.gxt` (the episodes fall back to the
   base game, like the game does) and writes the keys the pages use to
   `<out>/iv/<episode>/american.txt` (`iv/gxt2txt.py`).
2. Builds **whm2html** from `third_party/gtaweb` (a fork of
   [zeozeozeo/gtaweb](https://github.com/zeozeozeo/gtaweb)) with Go, once.
3. Exports the shared texture dictionaries the pages use (`pc/textures/web*.wtd`,
   adverts, browser, police computer...) to `_tex/<dictionary>/<texture>.png`.
4. Converts every `pc/html/**/*.whm` page to HTML and PNG.
5. Builds the fill layer (`iv/build_fill.py`): in the game several blocks of the pages
   (news, e-mail, dating profiles, police records, adverts) are filled by scripts while
   the game runs. The converter leaves them as marked slots and `_fill/fill.js` fills
   them in the browser from `_fill/data.js`, which is made from the game's own texts and
   textures.

Result: `<out>/iv/{GTAIV,TLAD,TBoGT}/pc/html/` with about 726 pages and 3,700 files. The
server shows an index at `/iv/` and the three episodes under `/r0/`, `/r1/` and `/r2/`
(TBoGT is `/r1/`, TLAD `/r2/`).

Expected time: about 75 seconds once the converter is built; the first build also
downloads Go (when it is not installed) and the converter's Go modules, about 3 minutes
in total.

Other GTA IV tools in `iv/`, for people who want to look inside the files:

- `iv/gxtdump.py <american.gxt>`: list the tables and how many strings each has.
- `iv/gxt2txt.py`: the GXT reader used by the build (keys are Jenkins one-at-a-time
  hashes of the lower-case key name).
- `iv/gxtbrute.py`: recover key names from their hashes by combining likely words.

## The classic sites (GTA III, Vice City, San Andreas)

Those games have no in-game internet. What they had were the websites Rockstar published
at the time: sites set in the game's world (Liberty Tree, Love Media, Kent Paul,
Degenatron, Exsorbeo, Epsilon Program...) and promotional sites. They no longer exist;
copies of them are kept by the Internet Archive.

```sh
python build.py classic                # or: python classic/build_classic.py [options]
```

Options of `classic/build_classic.py`:

| Option | Meaning |
|---|---|
| `--only ID[,ID]` | only these sites (ids in `classic/classic_sites.json`) |
| `--offline` | no network: rebuild `out/` from the download cache |
| `--delay 0.8` | seconds between two requests (keep it) |
| `--workers 1` | parallel downloads (keep it at 1, see below) |
| `--keep` | do not delete `<out>/classic` first |
| `--refresh` | list the sites from the CDX API instead of the lock files (maintainers) |

What it does:

1. **List.** `classic/classic_sites.json` names the 29 sites, their URL prefixes and the
   time window of each. `classic/lock/<site>.json` pins every file of a site: its URL,
   the capture to download (`cap`, a Wayback timestamp) and the SHA-1 of its bytes
   (`sha1`). There are 3,961 rows for about 3,700 distinct files.
2. **Download** each file once, as the original bytes the Archive stored
   (`https://web.archive.org/web/<cap>id_/<url>`), into `<work>/classic/<GAME>/_raw/`.
   Files already in the cache with the pinned SHA-1 are not downloaded again.
3. **Repair** what the Archive does not have (`classic/raw_fixes.py`). Every rule looks
   for a pattern and checks what was archived, and what it changes is marked in the page
   with a `gta-web-local:` comment:
   - video players (QuickTime, Windows Media, RealPlayer): almost no video was archived
     and none is downloaded; the player becomes a box of the same size saying so;
   - Flash movies that were never archived: the same kind of box;
   - MIDI music embedded with a plug-in: a link to the file;
   - trackers and dead third-party services (Urchin, Google Analytics, AddThis,
     Facebook, a web-font service, ad servers) are removed;
   - Flash detectors that run before Ruffle is ready, and the "moock fpi" pages that load
     their detection from another server, now go straight to the Flash page when its
     SWF was archived, or to the page without Flash otherwise;
   - frames that showed another server (contest forms, stores, toolbars) show a short
     note, or the copy of those pages that the site itself kept;
   - hit counters only pick the counter images that were archived;
   - for the two sites that exist both on their own domain and under
     rockstargames.com, links to files only archived in the other copy point there;
   - pages that submitted a form on load to a script the Archive cannot answer show a note.
4. **Rewrite** the links so the pages work locally under `/iii/`, `/vc/` and `/sa/`,
   and add [Ruffle](https://ruffle.rs) (a Flash player in WebAssembly) to every page.
   Ruffle 0.2.0-nightly.2026.1.22 comes from the npm registry (SHA-512 checked).

The cached files in `<work>/classic/<GAME>/_raw/` are never modified: every build starts
again from the original bytes, so the result only depends on the lock files and on the
code.

Result: `<out>/classic/<GAME>/<host>/<path>` (about 3,700 files, 888 pages),
`<out>/classic/_sites.json` (the hub's list) and `<out>/_ruffle/`.

### Expected time

| Build | Time |
|---|---|
| First build (empty `work/`) | about 2 hours: 3,700 requests, one at a time, 0.8 s apart, plus the Archive's own response time (111 minutes in our test) |
| Later builds | under a minute: everything comes from the cache |
| `--offline` | about 10 seconds |

The download can be interrupted and started again: files already in the cache are kept.

### Being polite to the Internet Archive

The Internet Archive is a non-profit library that serves these files for free. The
mirror is written to ask as little as possible of it:

- It downloads **one file at a time** (`--workers 1`), waiting `--delay 0.8` seconds
  between requests, over **one kept-alive HTTPS connection**. The Archive limits how
  many new connections a client opens; the mirror never needs more than one.
- When the Archive refuses connections or answers 429/5xx, the mirror waits (a minute
  for refused connections, an increasing pause for errors) instead of insisting.
- Every file is downloaded **once**: later builds use the cache in `work/`. Keep that
  folder if you will build again, and do not delete it to "start clean"; use
  `--offline` to rebuild `out/` from it.
- The lock files name the exact captures, so a build never needs the CDX search API.
  `--refresh` (which lists every site again through the CDX API) is for maintainers who
  want to update the lock files, not for normal builds.
- Requests identify the project in their User-Agent.

Please do not raise `--workers` or lower `--delay`. If you want to support the Archive,
consider a donation at <https://archive.org/donate>.

### What the Archive does not have

Some things were never archived and cannot be rebuilt by anyone:

- **Video.** The trailers and in-game videos the sites offered (QuickTime, Windows
  Media) were almost never captured; their players are replaced by a box.
- **Some Flash movies** (a few navigation bars, retail mini-sites, one Degenatron game)
  were never captured; they are replaced by a box.
- **About 115 images** (and a few scripts and pages) that pages ask for were never
  captured; about 140 of the 888 pages show a missing image or a failed request, as
  they would in the Wayback Machine.
- **Server-side features**: forms, contests, e-mail sign-ups, store frames.

Flash runs in Ruffle, which plays most of these movies; a few use features Ruffle does
not have yet.

## Serving

```sh
python serve.py [--port 8044] [--no-browser] [--config file] [--out folder]
```

`/` is a hub with every game; `/iv/` the GTA IV index; `/iii/`, `/vc/`, `/sa/` the classic
sites; `/v/` GTA V when built. The server only reads `out/` and binds to 127.0.0.1.

## Checking a build

Two builds of the same inputs are byte-identical, so a build can be compared with
another one file by file:

```sh
python tests/compare_trees.py <reference out>/classic <your out>/classic --exclude "*/_raw/*" --exclude "*/_manifest/*"
python tests/compare_trees.py <reference out>/iv <your out>/iv --html-normalize
```

`--html-normalize` compares HTML as tags with sorted attributes, for comparisons with GTA
IV builds made by converter versions that wrote attributes in random order.

The browser probe opens every page through the running server and reports failed
requests, broken images, raw text keys left visible, empty script slots and console
errors, with a screenshot per page:

```sh
npm install                                          # puppeteer-core
python serve.py --no-browser &
node tests/probe.mjs --base http://127.0.0.1:8044 --out out --iv --states tests/iv_states.txt --report probe/iv
node tests/probe.mjs --base http://127.0.0.1:8044 --out out --classic --report probe/classic
python tests/compare_probes.py probe/classic-old/report.json probe/classic/report.json
python tests/sheets.py probe/classic "vicecityradio" sheet.png      # contact sheet (Pillow)
```

A probe of the classic sites takes about 20 minutes (Ruffle is given 4 seconds per page);
GTA IV takes about 5 minutes.

## External services

| Service | Used by | When |
|---|---|---|
| `web.archive.org` (Wayback Machine, `id_` captures) | `build.py classic` | first build; then only files missing from the cache |
| `web.archive.org/cdx/search/cdx` (CDX API) | `build_classic.py --refresh` | only when a maintainer refreshes the lock files |
| `registry.npmjs.org` (Ruffle package, SHA-512 checked) | `build.py classic` | once, kept in `<work>/tools` |
| `go.dev/dl` (Go 1.27.1, SHA-256 checked) | `build.py iv` | once, only when `go` is not on PATH |
| `proxy.golang.org` (the converter's Go modules) | `build.py iv` | once, when the converter is built |
| `github.com` (the `third_party/gtaweb` submodule) | `git submodule update` | once |
| `registry.npmjs.org` (puppeteer-core) | `npm install` | only for the probe |

The served pages themselves load nothing from the internet, except images some classic
pages took from other servers at the time, which are requested from the Wayback Machine
when the page is opened.

## Updating the lock files (maintainers)

`--refresh` lists the sites again through the CDX API, keeps the rows added by hand to
the lock files and drops the ones they mark as `pruned`. To write new lock files from
the result:

```sh
python classic/wayback_mirror.py classic/classic_sites.json <out>/classic --cache <work>/classic \
    --lock classic/lock --refresh --assets-pass --externals --write-lock classic/lock
```

Then build again and compare the result with the previous build before committing the
new lock files.
