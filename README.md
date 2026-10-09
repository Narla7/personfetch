# personfetch

> **fastfetch, but for people.** 

A tiny CLI that renders *you* as a fastfetch/neofetch-style info card in your
terminal: a retro, palette-crushed portrait on the left, your editable
key/value fields on the right.

```console
$ personfetch
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   name: Narla
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   os: Arch Linx
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   interests: linux, code, music
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀   shell: Bash
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
...
```

(In real life the `▀` half-blocks are **colored** with your photo's pixels —
two terminal rows per line.)

> **Version:** 0.1.0 · **Language:** Python ≥ 3.11 · **Runtime dep:** Pillow — that's it

---

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
- [Theming & custom palettes](#theming--custom-palettes)
- [Configuration](#configuration)
- [Development](#development)
- [Tips](#tips)
- [License](#license)

---

## Features

- **Portrait as ANSI art** — any photo (JPG/PNG/whatever Pillow opens) gets
  EXIF-rotated, LANCZOS-downscaled, quantized to a limited palette (with
  Floyd–Steinberg dithering by default), and rendered with the upper-half
  block character `▀` — two pixels per terminal row.
- **Editable fastfetch-style fields** — add, change, or remove any
  `label: value` line. Labels are colored, per-field, with hex colors.
- **New fields get auto-colored** from your current palette (cycling through
  it, skipping the dark background colors), so you don't have to pick.
- **Built-in palettes**: `gruvbox` and `catppuccin`, plus drop-in custom
  palettes as JSON files.
- **Truecolor → 256-color fallback** handled automatically based on
  `COLORTERM`.
- **OS easter egg** — a default `os:` field is detected from `/etc/os-release`
  (`PRETTY_NAME`) on Linux, or `platform.system()` elsewhere.

## How it works

```text
your photo                profile.json           terminal
┌──────────────┐   copy   ┌───────────────┐    ┌─────────────────────────┐
│ me.jpg ──────┼──copy──► │ image_path: … │──► │ ▀▀▀▀▀▀▀▀▀    name: Narla│
│              │ ┌──────► │ palette: …    │    │ ▄▄▄▄▄▄▄▄▄    os: …      │
└──────────────┘ │ avatar  │ fields: [...]│    │ (halfblocks)  label: …  │
                 │  .png   └───────────────┘    └─────────────────────────┘
render pipeline (per run):
  open → exif_transpose → RGB → LANCZOS resize (width × ~2 rows/cell)
  → quantize to palette (with/without dither) → ▀ half-blocks with ANSI fg/bg
```

The copy of your photo lives at `~/.config/personfetch/avatar.png` — the
original file is never touched. If no image is set (or it fails to load), a
friendly placeholder face is shown instead.

## Installation

**Recommended — with [uv](https://docs.astral.sh/uv/):**

```bash
git clone <repo>
cd personfetch
uv tool install .
```

**With pipx:**

```bash
git clone <repo>
cd personfetch
pipx install .
```

**Without installing (run straight from the repo):**

```bash
uv run personfetch --help
```

**Update:** re-run `uv tool install . --force` (or `pipx install . --force`)
from a fresh clone/pull.

## Usage

```bash
personfetch init                                      # interactive first-time setup wizard
personfetch image ~/Pictures/me.jpg --palette catppuccin --width 34
personfetch                                           # show your card (default command)
personfetch set interests "linux, guitars,coding"
personfetch add pronouns  he/him                            # `add` is an alias for `set`
personfetch rm age                                    # what do you think it does???  
personfetch list                                      # plain-text dump of all fields
personfetch palettes                                  # what palettes exist
personfetch config                                    # print the profile.json path
```

Every command:

| Command | Arguments | What it does |
|---|---|---|
| *(none)* / `show` | `[--width N]` | Render your card. Default behavior. |
| `init` | — | Interactive wizard: name, age, location, OS, interests, extra fields, palette, dither, logo width, photo. |
| `set` / `add` | `label value [--color #hex]` | Create or update a field. `--color` sets the label color. |
| `rm` | `label` | Remove a field (case-insensitive label match). Unknown label → error, exit code 1. |
| `image` | `path [--palette NAME] [--width N] [--no-dither]` | Sets your portrait (copied to `avatar.png`), optionally switching palette/width/dither in the same go. |
| `list` | — | Print all fields as plain `label: value` lines. |
| `palettes` | — | List built-in + custom palette names. |
| `config` | — | Print the absolute path to `profile.json`. |

Global option: `personfetch --width N` forces the layout width if terminal
detection misbehaves. Logo width passed to `image`/`init` is clamped to the
10–120 range; at render time it shrinks in steps of 2 until logo + gutter +
info fits in the terminal.

Useful subcommand help: `personfetch image --help`, `personfetch set --help`.

## Theming & custom palettes

A palette is just a JSON list of hex colors. On first run the built-ins are
copied to `~/.config/personfetch/palettes/` so you can edit or add:

```console
$ personfetch palettes
Available palettes:
  - catppuccin
  - gruvbox
```

Add your own by dropping `~/.config/personfetch/palettes/<name>.json`:

```json
{
  "name": "mytheme",
  "description": "better theme",
  "colors": ["#282828", "#cc241d", "#98971a", "#d79921", "#458588"]
}
```

Rules of the road:

- `colors` is a list of `#rrggbb` (or `#rgb`) hex strings — order matters for
  the auto-color cycling of new fields, and the first few entries tend to act
  as backgrounds/darks.
- A custom palette file **overrides** a built-in of the same name (that's how
  you'd re-skin `gruvbox` without a new name).
- `name`/`description` are optional metadata; only `colors` is required
  (a legacy `palette` key is also accepted).
- Invalid hex in a custom file → loader silently falls back to the built-in
  with that name, else `gruvbox`. Set with `personfetch image <path>
  --palette mytheme`.
- Dithering off (`--no-dither`) = chunkier retro blocks on; on = smoother
  gradients. Try both.

## Configuration

Everything lives in an XDG-compliant config dir:

```text
~/.config/personfetch/          (respects $XDG_CONFIG_HOME)
├── profile.json                profile card + display settings
├── avatar.png                  your copied photo
└── palettes/
    ├── gruvbox.json
    ├── catppuccin.json
    └── *.json                  your custom palettes
```

`profile.json`, verified defaults (created automatically on first run; missing
keys are backfilled when an older file is loaded):

| Key | Default | Meaning |
|---|---|---|
| `version` | `1` | Config schema version. |
| `image_path` | `null` | Points at `avatar.png`. `null` = placeholder face. |
| `palette` | `"gruvbox"` | Any name from `personfetch palettes`. |
| `logo_width` | `34` | Portrait width in terminal cells (range 10–120 when set via CLI). |
| `gutter` | `3` | Spaces between portrait and info column. |
| `dither` | `true` | Floyd–Steinberg dithering during quantization. |
| `separator` | `":"` | Between label and value (e.g. `" → "` if you're fancy). |
| `fields` | name / age / os / interests | List of `{label, value, color}` objects. |

`fields` entries are plain JSON — you can hand-edit them (or the whole file)
and the next `personfetch` run just works. The default `name`/`age` values are
the author's starter example: run `personfetch set name "Your Name"` to make
it *yours*.

## Development

```bash
git clone <repo>
cd personfetch
uv sync                 # create .venv + install deps (Pillow only)
uv run personfetch      # run without installing

uv build                # build sdist/wheel
```

Layout (src-layout, `uv_build` backend):

```text
src/personfetch/
├── __main__.py    # argparse CLI + subcommand handlers
├── __init__.py    # __version__
├── profile.py     # config dir, profile.json load/save/migrate, field ops, OS detect
├── render.py      # card layout: logo column + colored info column
├── image.py       # Pillow pipeline + ANSI half-block renderer + color fallback
├── palettes.py    # built-ins, JSON loading, custom palette discovery
└── wizard.py      # `init` interactive setup
```

Fixing/adding something? Keep it dependency-light, keep paths XDG-compliant,
and make the first run never break — profiles are saved atomically
(`.tmp` → replace) and unknown keys are tolerated on load.

## Tips

- Shell prompt flex: run it in your `.zshrc`/`config.fish` for interactive
  shells only, with a small width. Duplicate a field for a fun second session
  name: `personfetch set mood "caffeinated"`.
- Value tips: quotes matter (`personfetch set interests "a, b, c"`), URLs and
  emoji are fine in values, and labels are lowercase-matched: `RM Name` removes `name`.
- Structure your palette dark→light (background colors first) to get the best
  auto-label colors for new fields.
- `personfetch config` gives you the exact `profile.json` path for direct editing.
- Breakage recovery: `rm -rf ~/.config/personfetch && personfetch init` nukes
  and rebuilds everything. Your original photos are never modified — only the
  copied `avatar.png`.

## Limitations

- Terminal renderers only — half-block art assumes a monospace font at a
  normal cell aspect ratio; extreme fonts/line-heights may stretch the image.
- 256-color fallback approximates hues — truecolor terminals
  (`COLORTERM=truecolor|24bit`) get exact palette colors.
- No Windows-specific OS detection polish: falls back to `"Windows"` /
  `"Darwin"` from `platform.system()`.

## License

MIT — see the [LICENSE](LICENSE) file for details.
