# GTA V: the story-mode websites

`v/build_v_sites.py` rebuilds the 81 websites of the in-game browser of GTA V's story mode
(eyefind.info, bleeter.biz, lifeinvader.com, the banks, the stock markets, the vehicle
dealers...) from **your own GTA V install**, and `serve.py` shows them at `/v/`. Each page
is the game's own Flash movie (Scaleform GFx) converted to a plain SWF that
[Ruffle](https://ruffle.rs) can play, running inside the game's own browser movie, with
the game's textures, fonts and text.

Nothing from the game is stored in this repository. Every image, text, font and data
table is read from your install while building and written to your `out` and `work`
folders, which are git-ignored.

- 81 story-mode sites (the six Online-only sites of the game are left out: they are not
  in the base archive).
- 15 of them were republished by Rockstar in `update.rpf`; both versions are built. The
  current one opens by default and the 2013 one opens with `?version=2013`.
- The 10 dynamic sites, whose content the game's browser script fills in at run time
  (banks, stock markets, Lifeinvader, eyefind news, bleeter, Epsilon...), get that data
  from your own `appinternet.ysc`, run in a small script VM, or from hand-written
  providers (see [Host and providers](#host-and-providers)).

## Requirements

| What | Version | Notes |
|---|---|---|
| GTA V for PC | **Enhanced** (tested) or Legacy (implemented, not tested) | Read only. The folder that contains `x64b.rpf` and `GTA5_Enhanced.exe` / `GTA5.exe` |
| Python | 3.11 or newer (tested 3.11.3) | Uses `tomllib` |
| Pillow | 10 or newer (tested 12.2.0) | `pip install Pillow`. Decodes the DDS textures and writes PNG |
| Java | 8 or newer (tested OpenJDK 21.0.11) | For JPEXS FFDec. `java` on PATH or `JAVA_HOME` set |
| Internet access | first run only | To download the tools below |
| Disk space | about 2.5 GB | `<work>/tools` ~0.8 GB (0.7 GB of it is the .NET SDK, when it has to be installed), `<work>/v` ~1.2 GB, `<out>/v` ~390 MB |
| OS | Windows x64 (tested) | Linux x64 should work (rage-cli, .NET and JPEXS exist for it) but is not tested |

Downloaded by the build into `<work>/tools` at pinned versions (`v/thirdparty.py`).
Nothing is vendored. rage-cli, JPEXS and CodeWalker are checked against SHA-256 digests
and Ruffle against its npm SHA-512 integrity; the .NET SDK is pinned by version and
installed by Microsoft's script, and NuGet checks the package signatures:

| Tool | Version | Source | License | Used for |
|---|---|---|---|---|
| rage-cli | 0.22.0 | <https://github.com/VIRUXE/rage-cli/releases/tag/v0.22.0> | Unlicense | Listing and extracting RPF archives. It reads the archive keys from your own game executable (cached in `<work>/tools/rage-keys`) |
| JPEXS FFDec | 26.3.0 | <https://github.com/jindrapetrik/jpexs-decompiler/releases/tag/version26.3.0> | GPL-3.0 (the CLI); its libraries are LGPL-3.0 | ActionScript export of the site movies (text labels, the 2013 vehicle tables) and compiling the host shim |
| CodeWalker (source) | commit `485d56bec00262ed7fa472261cce7bbc6202b96e` | <https://github.com/dexyfex/CodeWalker> | No license file; the author releases the source "for educational purposes" | Only `CodeWalker.Core` is compiled, to read `.ytd` texture dictionaries (gen9 textures of the Enhanced edition included) |
| .NET SDK | 8.0.425 | Microsoft's `dotnet-install` script (<https://dot.net/v1/dotnet-install.ps1>, `.sh`) | MIT | Compiling `v/ytdexport` against CodeWalker.Core. Only installed when no .NET 8+ SDK is on PATH (then that one is used) |
| SharpDX, SharpDX.Mathematics | 4.2.0 | NuGet, restored by `dotnet build` (pinned by CodeWalker.Core's project file) | MIT | Dependencies of CodeWalker.Core |
| Ruffle | 0.2.0-nightly.2026.1.22 | npm `@ruffle-rs/ruffle` (pinned in `classic/build_classic.py`) | MIT or Apache-2.0 | The Flash player of the pages. Copied to `<out>/_ruffle/` only when the classic build has not put it there already |

Optional, only for the `shoot` stage (index thumbnails) and for checking the build in a browser:

| What | Version |
|---|---|
| Node.js | 18 or newer (tested 22.20.0) |
| puppeteer-core | 25.12.0 (`npm install` at the repository root) |
| Chrome, Chromium or Edge | any recent one. Auto-detected, or set `CHROME_PATH` |

## Building

```sh
cp config.example.toml config.toml        # set gta5 = the folder that contains x64b.rpf
python v/build_v_sites.py                 # or: python build.py v
python serve.py                           # http://127.0.0.1:8044/v/
```

A first run from an empty `work` folder took 8 minutes on the test PC (20 threads, fast
connection), downloads included. Later runs skip what is up to date.

```sh
python v/build_v_sites.py --force                     # redo every stage
python v/build_v_sites.py --stages text,convert,pages # only some stages
python v/build_v_sites.py --only bawsaq,eyefind       # convert/pages of some sites only
python v/build_v_sites.py --stages shoot,thumbs,index # optional: thumbnails for the index
python v/build_v_sites.py --prefer base               # the 2013 version opens by default
python v/build_v_sites.py --config other.toml         # another config file
python v/thirdparty.py [--check]                      # only the tools
python v/extract.py [--steps web,lang] [--force]      # only the extraction
```

### Stages

The default stages run in this order. Each one checks its inputs and skips work that is
already done.

| Stage | What it does | Output |
|---|---|---|
| `tools` | Downloads rage-cli, JPEXS, CodeWalker and, if needed, the .NET 8 SDK, then compiles `v/ytdexport` against CodeWalker.Core | `<work>/tools` |
| `extract` | `v/extract.py`, with rage-cli: the 2013 sites (`x64b.rpf/.../scaleform_web.rpf`), `scaleform_generic.rpf` (base and update), the font libraries and `fontmap.xml`, the American English GXT2 text (`update2.rpf` and the `update.rpf` patch), the `global.gxt2` of every DLC pack, `appinternet.ysc` (current and 2013), and the site textures (ytdexport, then DDS to PNG) | `<work>/v/extract` |
| `update` | The current versions of the 15 sites republished in `update.rpf`, their textures, the texture dictionaries they request at run time, and `web_browser.gfx` | `<work>/v/assemble`, `<work>/v/host/src` |
| `decompile` | JPEXS ActionScript export of the site movies and of the browser | `<work>/v/as` |
| `scripts` | `v/scriptdata`: runs your `appinternet.ysc` in a small VM and records what it would send to the sites: vehicle prices (current and 2013), eyefind news, bleeter pages, the Lifeinvader tables | `<work>/v/scriptdata` (`host_data.json`, `www.lifeinvader.com.js`) |
| `text` | `v/gxt2json.py`: the labels the sites, the script and the providers use (`strings_web.json`), the whole `global.gxt2` by hash with DLC and patch applied (`strings_global.json`), and the Epsilon subtitles | `<work>/v/text` |
| `convert` | `v/gfx2swf.py`, in parallel: each `.gfx` plus its textures and fonts becomes a Ruffle-ready `site.swf`. The other version of a site goes to `_lib/alt/<domain>/site.swf` | `<out>/v/<domain>/site.swf` |
| `browser` | The game's `web_browser` movie, converted the same way, with the host shim (`v/host/*.as`) compiled by JPEXS and injected | `<out>/v/_lib/web_browser.swf` |
| `lib` | Publishes `host.js`, the text tables, `host_data.json`, the providers and `gfxfontlib.swf`, and Ruffle if it is missing | `<out>/v/_lib`, `<out>/_ruffle` |
| `runtime` | The `news_*`, `char_*`, `dyn_mp_*` and `dia_*` texture dictionaries of `scaleform_generic.rpf` that the sites request at run time | `<work>/v/assemble/runtime` |
| `tex` | Publishes the run-time textures as `/v/_tex/<dictionary>/<texture>.png` | `<out>/v/_tex` |
| `pages` | One `index.html` per site (`v/shell.html` plus its configuration) | `<out>/v/<domain>/index.html` |
| `sites` | The site list (mode, notes, versions) | `<out>/v/_sites.json` |
| `thumbs` | Index thumbnails from the `shoot` screenshots, if there are any | `<out>/v/_lib/thumbs` |
| `index` | The `/v/` index page. Without thumbnails it uses the game's own eyefind thumbnails | `<out>/v/index.html` |

Optional stage, run only when named in `--stages`:

| Stage | What it does |
|---|---|
| `shoot` | Serves `<out>` on a free local port, opens every site in Chrome with `v/shoot/shoot.mjs` (one browser per site) and saves a screenshot of each one to `<work>/v/shots`. Run `thumbs,index` after it. It is skipped with a message when Node.js, puppeteer-core, Chrome or Ruffle are missing |

`v/shoot/shoot.mjs` is also a load check for a running server:

```sh
node v/shoot/shoot.mjs --base http://127.0.0.1:8044/v --out shots                 # the 81 sites
node v/shoot/shoot.mjs --base http://127.0.0.1:8044/v --out shots --version 2013  # the 15 2013 versions
```

It writes a screenshot per site and `manifest.json`. A site counts as loaded when the
game's browser reached it, the host reported `pageready`, it did not end on eyefind's error
page and no loading banner is left. The exit code is 0 when every site loaded.

## Using the pages

`/v/` lists the sites. Each page shows the game's browser at 1280×627 (the site area),
with the address bar of the page above it (back, forward, home = eyefind.info, address)
and, under the player, a note on whatever is simulated. Links between sites work like in
the game.

| Parameter | Effect |
|---|---|
| `?page=PAGE` | Opens a page of the site by its id (`PAGE1`, `NEWS`, ...) |
| `?version=2013` / `?version=actual` | The other version of a site that has two |
| `?personaje=michael\|franklin\|trevor` | The character, as the phone skin and as `browser.player` (the banks only know their own customer) |
| `?debug=1` | Host log in the console, missing labels shown as their names |

## What comes from where

| From your game (generated, never committed) | Hand-written (in this repository) |
|---|---|
| The 81 site movies, `web_browser`, the font libraries, every texture | `v/gfx2swf.py`: the GFx to SWF converter |
| All the text (GXT2 tables, by label and by hash) | `v/host.js`, `v/shell.html`: what the game engine does for the browser |
| Vehicle prices, eyefind news, bleeter pages, Lifeinvader tables (computed by running `appinternet.ysc`) | `v/host/*.as`: the ActionScript shim injected into the browser movie |
| The 2013 vehicle tables (from the decompiled 2013 movies) | `v/providers/*.js`: data for the dynamic sites |
| | `v/scriptdata/`: the ysc VM and the code that locates and runs the script functions |

### Script data

The browser script `appinternet.ysc` (from `update2.rpf` on Enhanced, `update.rpf` on
Legacy, plus the 2013 one from `x64b.rpf`) is run in `v/scriptdata/ysc.py`, a small
interpreter of the YSC bytecode (RSC7 v10 and v12, both opcode tables). The functions are
found by what they do (the strings they push, the calls they make), not by address, and
are checked against their expected parameter and return counts before they run. The game
state they see is a story-complete save: every story mission and random-character
mission done, no network game, Frogger unlocked. When the layout of a script does not
match, the `scripts` stage stops with a `ScriptLayoutError` instead of guessing.

## Host and providers

In the game, `web_browser.gfx` is the main movie and loads each site inside itself;
the browser script and the engine answer its calls. Here `v/host.js` plays that part:

- It starts Ruffle with `_lib/web_browser.swf` and asks it for a site with
  `GO_TO_WEBPAGE`, exactly as the script does. The browser movie does its own hit-testing,
  scrolling, history and error page.
- The shim (`v/host/host_pre.as`, `host_post.as`) adds `HOST_INVOKE`, `HOST_SET` and
  `HOST_GET` to the movie and routes `GameInterface.call` to JavaScript
  (`ExternalInterface`).
- It answers the movie's requests: text labels (`SET_TEXT_WITH_TRANSLATION`, from
  `strings.json`, with `strings_all.json` loaded in the background for the rest), site
  movies (`REQUEST_GFX_STREAM`), run-time textures (`img://<txd>/<tex>` to `/v/_tex/`),
  mouse, wheel, keyboard and touch input.
- On every page shown on a dynamic site it empties the data slots, calls the site's
  provider and ends with `UPDATE_TEXT`, like the script does.

Providers live in `v/providers/` and are published to `/v/_lib/providers/`.
`index.json` lists the domains that have one and their shared dependencies (`_*.js`); the
host only loads the files of the listed domains. A provider registers itself:

```js
GTAHOST.registerProvider('www.example.com', {
  onPage(pageName, api) { /* fill the data slots of this page */ },
  onSelect(selection, api) { /* optional: after each click (GET_CURRENT_SELECTION) */ },
  clearSlots: true,   // optional: empty the slots before onPage (default on dynamic sites)
});
```

`onPage` may be `async`. The `api` object it receives has, among others:

| Member | What it is |
|---|---|
| `page`, `pageId`, `siteId`, `domain`, `fullURL`, `fresh` | The page shown; `fresh` is true on the first page after entering the site |
| `character`, `characterName` | 0/1/2, `MICHAEL`/`FRANKLIN`/`TREVOR` |
| `state` | An object kept for the site while the page is open |
| `data` | `host_data.json` |
| `text(label, ...parts)`, `html(label, ...parts)`, `raw(label)`, `has(label)`, `byHash(hash)`, `need(labels)` | Game text, as plain text or HTML, with `~a~`/`~1~` substitutions |
| `setDataSlot(slot, ...values)`, `appendDataSlot`, `setDataSlotEmpty()`, `updateText()` | `SET_DATA_SLOT`, `APPEND_DATA_SLOT`, `SET_DATA_SLOT_EMPTY`, `UPDATE_TEXT` |
| `goTo(target)`, `refresh()`, `getSelection()` | `GO_TO_WEBPAGE`, refill the current page, `GET_CURRENT_SELECTION` |
| `callMovie(method, ...args)`, `callSite(method, ...args)`, `invoke/get/set` | Direct calls into the browser movie or the loaded site |
| `note(text)` | A note under the player while this site is shown |
| `isCurrent()`, `log(...)` | Is this page still shown; write to the host log |

Labels used by a provider must be quoted literally in its file (`'BNK_...'`) or built
from a quoted prefix (`'PREFIX_' + n`): the `text` stage scans the providers to decide
which labels go into `strings.json`. Rerun `--stages text,lib` after adding labels.

## Reproducibility

Two builds from the same game files give the same `out/v`:

- `site.swf`, `web_browser.swf`, `gfxfontlib.swf` and the JSON files are deterministic.
- The `?v=` cache stamps in the pages are content hashes, not dates.
- PNG files are written by Pillow. Another Pillow or zlib version can compress them
  differently, but the pixels are the same.
- The JPEXS ActionScript export is only used for label names and the 2013 vehicle
  tables. Another JPEXS version can format the code differently, but it gives the same
  literals.

## Known limitations

- **Only the Enhanced edition has been tested end to end.** The Legacy code paths exist
  (`GTA5.exe`, the RSC7 v10 script format and its opcode table, which is the format of the
  2013 script in `x64b.rpf`, non-gen9 textures through CodeWalker, the `update.rpf` text),
  but no Legacy install has been built with them.
- The page interface (index, address bar, notes under the player) is in Spanish. The
  game text is the American English one.
- What the game takes from your save is simulated, with a note under the player:
  Lifeinvader shows a story-complete profile and wall; eyefind news and bleeter show the
  whole story; bank balances and transactions are invented (the transaction names and
  some amounts are the game's); the stock markets have invented prices and charts, and
  purchases are not made; Children of the Mountain starts at the beginning, as Franklin.
- The banks open with their own customer (Maze Bank: Michael, Fleeca: Franklin, Bank of
  Liberty: Trevor); with another character they reject the user, as in the game.
- Epsilon's video presentation has subtitles but no audio. There is no sound at all.
- The current warstock site asks for 14 Online labels (`CANDC_HACKER_*`, `CANDC_SUB_*`)
  that no game text table has; they belong to Online panels that story mode hides.
- Vehicle prices: the script VM also prices 7 vehicle ids (6 of legendarymotorsport, 1
  of warstock) that are not in those sites' story-mode lists, so the pages do not show
  them.
- The game's on-screen keyboard appears for search boxes; type with the physical
  keyboard. Mobile keyboards do not open.
- The Ruffle console may show "Export asset ... not found" warnings from the font
  library (GFx exports without a character); they have no effect.

## Files

```
v/
  build_v_sites.py     the build (stages above)
  thirdparty.py        tool downloads (pinned versions and checksums)
  extract.py           what is read from the game install
  gfx2swf.py           GFx (Scaleform) to SWF converter for Ruffle
  gxt2json.py          GXT2 text tables to JSON
  host.js, shell.html  the page and the game side of the browser
  host/                the AS2 shim (*.as) and the tools that inject it into web_browser.swf
  providers/           data providers of the dynamic sites
  scriptdata/          ysc VM and the script data ports (prices, eyefind, bleeter, Lifeinvader)
  ytdexport/           texture exporter (C#, compiled against CodeWalker.Core)
  shoot/shoot.mjs      load check and screenshots (optional)
```
