# GTA Web Local

*[Leer en español](README.es.md)*

Browse the in-game websites of the Grand Theft Auto saga on your own computer, the way
they look inside the games:

- **GTA IV**, **The Lost and Damned** and **The Ballad of Gay Tony**: the whole in-game
  internet of Liberty City (eyefind.info, love-meet.net, the LCPD database, Weazel News,
  your in-game e-mail...), about 726 pages converted from the game's own files, with the
  blocks the game fills in with scripts (news, dating profiles, police records, adverts)
  filled in as well.
- **GTA V** (story mode): the 81 websites of the in-game browser (eyefind, bleeter,
  Lifeinvader, the banks, BAWSAQ and LCN, Legendary Motorsport, Elitás Travel, the
  Epsilon Program, The Children of the Mountain...), each one the game's own Flash movie
  converted for [Ruffle](https://ruffle.rs) and running inside the game's own browser.
- **GTA III**, **Vice City** and **San Andreas**: those games have no in-game internet,
  so this rebuilds the 29 websites Rockstar published for them at the time (Liberty
  Tree, Love Media, Kent Paul, Degenatron, Exsorbeo, the Epsilon Program...) from the
  Internet Archive's Wayback Machine.

Everything is served by one small local server with an index of all five games at
`http://127.0.0.1:8044/`.

## No game files in this repository

This repository contains **only code**. It has no pages, images, fonts, texts or data
from the games and nothing downloaded from the Internet Archive. You build everything on
your own computer:

- GTA IV and GTA V are converted from **your own installed copy** of the game.
- The GTA III / Vice City / San Andreas sites are downloaded by your computer from the
  Wayback Machine. Every file is pinned to a capture and a checksum (`classic/lock/`), so
  everybody gets the same bytes.

The builds are reproducible: the same game files give byte-for-byte the same output.

## Quick start

You need **Python 3.11+** and **Git**. GTA V also needs **Java 8+** and Pillow
(`pip install -r requirements.txt`). Go, the .NET SDK, Ruffle and the other tools are
downloaded at pinned versions the first time they are needed.

```sh
git clone --recurse-submodules https://github.com/memorx/gta-web-local
cd gta-web-local
cp config.example.toml config.toml     # on Windows: copy config.example.toml config.toml
# edit config.toml: point gta4 / gta5 at your game folders (leave one empty to skip it)

python build.py iv          # GTA IV + episodes          (~3 minutes the first time)
python build.py v           # GTA V story-mode sites      (~8 minutes the first time)
python build.py classic     # III / VC / SA from the Wayback Machine (~2 hours the first time)
python build.py             # or everything at once

python serve.py             # then open http://127.0.0.1:8044/
```

`config.toml`:

```toml
[paths]
gta4 = "C:/Program Files (x86)/Steam/steamapps/common/Grand Theft Auto IV/GTAIV"
gta5 = "C:/Program Files (x86)/Steam/steamapps/common/Grand Theft Auto V"
out  = "out"     # what the server shows
work = "work"    # extracted files, caches and downloaded tools (can be deleted)
```

The game folders are only read, never written.

## Documentation

- [docs/iv-and-classics.md](docs/iv-and-classics.md): GTA IV and the classic sites:
  requirements, every step, durations, the Wayback lock files and how to check your build.
- [docs/gta-v.md](docs/gta-v.md): GTA V: requirements, the build stages, how the
  dynamic sites get their data (a small VM runs your own `appinternet.ysc`), the host
  that stands in for the game, and the known limitations.
- [third_party/README.md](third_party/README.md): the GTA IV page converter (submodule).

Tested on Windows 11 with GTA IV Complete Edition (Steam) and GTA V Enhanced. GTA V
Legacy and Linux are implemented but not tested yet.

## Layout

| Folder | What |
|---|---|
| `build.py`, `serve.py` | build any part, start the server |
| `server/` | the local server and the index pages |
| `iv/` | GTA IV build: GXT reader, texture export, the fill layer for script-filled blocks |
| `third_party/gtaweb` | **whm2html**, the `.whm` → HTML converter (fork of zeozeozeo/gtaweb, git submodule) |
| `classic/` | Wayback Machine mirror, lock files and the repair rules for old pages |
| `v/` | GTA V build: extraction, GFx → SWF converter, script VM, host and data providers |
| `tests/` | browser probes and output comparisons |

## Credits

- [zeozeozeo/gtaweb](https://github.com/zeozeozeo/gtaweb): the original GTA IV `.whm`
  converter this project's fork is based on.
- [Ruffle](https://ruffle.rs): the Flash Player emulator that plays the GTA V sites and
  the old Flash sites.
- [rage-cli](https://github.com/VIRUXE/rage-cli), [CodeWalker](https://github.com/dexyfex/CodeWalker)
  and [JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler):
  reading the GTA V archives, textures and Flash movies.
- The [Internet Archive](https://archive.org): without the Wayback Machine the GTA III,
  Vice City and San Andreas sites would be gone. Please be gentle with it: the build
  downloads one file at a time on purpose.
- The [GTA Wiki](https://gta.fandom.com) community, whose screenshots of the real games
  were used to check that every GTA V site looks right.

## License and legal

The code in this repository is under the [MIT License](LICENSE). The tools the build
downloads keep their own licenses.

Grand Theft Auto and everything in it (the websites, their texts, images and fonts) are
the property of Rockstar Games and Take-Two Interactive. This is a non-commercial fan
project, not affiliated with or endorsed by them. You need your own legally obtained
copy of the games; do not share the generated output.
