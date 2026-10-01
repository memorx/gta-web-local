# third_party

## gtaweb (git submodule)

`third_party/gtaweb` is the GTA IV page converter, **whm2html**, written in Go. It
reads the game's `.whm` pages (RSC5 + zlib) and `.wtd` texture dictionaries and
writes HTML and PNG.

- Upstream: <https://github.com/zeozeozeo/gtaweb> by zeozeozeo. The upstream
  repository has **no license**, so none of its code is copied into this
  repository; it is referenced as a git submodule instead.
- Submodule: <https://github.com/memorx/gtaweb>, branch `liberty-web`: upstream
  commit `db47406` plus our changes as separate commits:
  - paths for the source, output and localization file on the command line
  - sites that do not start with `www.` (mail.eyefind.info, the blogsnobs.org blogs...)
  - font path relative to the output root; no image preload lists; no index pages
  - images from shared texture dictionaries (`dict:texture`) linked to `_tex/<dict>/<texture>.png`
  - script-filled objects kept as `<span class="scriptobj" data-name="...">` slots, and every
    page loads the fill layer (`_fill/fill.css`, `data.js`, `fill.js`) built by `iv/build_fill.py`
  - `whm2html wtd <file.wtd> <out_dir>` and `whm2html dump <file.whm>`
  - attributes written in a stable order, so two builds of the same files are byte-identical

`iv/build_iv.py` builds the converter from this folder with Go (it downloads a pinned
Go release into `<work>/tools/go` when `go` is not on PATH) and runs it. Nothing in
the submodule is modified by the build.

Setting it up:

```sh
git submodule update --init third_party/gtaweb
```

Note: the upstream repository also contains its own converted pages and a font
(`iv/`, `v/`, `ttf/`). This project does not use their pages; `ttf/DIN-Medium.woff2`
is copied into the build output because the converted pages ask for it.
