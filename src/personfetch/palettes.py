"""Palette definitions and loader for personfetch.

Palettes are stored as JSON files in the user's config directory under
``palettes/``. The built-in palettes are copied there on first run so users
can edit them or add their own.
"""

from __future__ import annotations

import json
from pathlib import Path


Palette = list[tuple[int, int, int]]


BUILTIN_PALETTES: dict[str, Palette] = {
    "gruvbox": [
        (40, 40, 40),
        (204, 36, 29),
        (152, 151, 26),
        (215, 153, 33),
        (69, 133, 136),
        (177, 98, 134),
        (104, 157, 106),
        (168, 153, 132),
        (146, 131, 116),
        (251, 73, 52),
        (184, 187, 38),
        (250, 189, 47),
        (131, 165, 152),
        (211, 134, 177),
        (142, 192, 124),
        (235, 219, 178),
    ],
    "catppuccin": [
        (30, 30, 46),
        (17, 17, 27),
        (24, 24, 37),
        (243, 139, 168),
        (166, 227, 161),
        (249, 226, 175),
        (137, 180, 250),
        (203, 166, 247),
        (180, 190, 254),
        (148, 226, 213),
        (137, 220, 235),
        (245, 194, 231),
        (242, 205, 205),
        (238, 212, 159),
        (205, 214, 244),
        (147, 153, 178),
    ],
}


def hex_to_rgb(hexcolor: str) -> tuple[int, int, int]:
    """Convert ``#rrggbb`` or ``#rgb`` to an RGB tuple."""
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hexcolor!r}")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert an RGB tuple to ``#rrggbb``."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _palette_to_dict(palette: Palette) -> dict:
    return {
        "name": "custom",
        "description": "",
        "colors": [rgb_to_hex(r, g, b) for r, g, b in palette],
    }


def _palette_from_dict(data: dict) -> Palette:
    colors = data.get("colors", data.get("palette"))
    if not isinstance(colors, list):
        raise ValueError("Palette must contain a list of hex colors")
    return [hex_to_rgb(c) for c in colors]


def load_palette_file(path: Path) -> Palette:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _palette_from_dict(data)


def palettes_dir(config_dir: Path) -> Path:
    d = config_dir / "palettes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_builtin_palette_files(config_dir: Path) -> None:
    """Write the built-in palettes to the user's config dir if missing."""
    d = palettes_dir(config_dir)
    for name, palette in BUILTIN_PALETTES.items():
        p = d / f"{name}.json"
        if p.exists():
            continue
        with p.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": name,
                    "description": f"Built-in {name} palette",
                    "colors": [rgb_to_hex(r, g, b) for r, g, b in palette],
                },
                f,
                indent=2,
                ensure_ascii=False,
            )


def list_palettes(config_dir: Path) -> list[str]:
    names = set(BUILTIN_PALETTES.keys())
    d = palettes_dir(config_dir)
    for p in d.glob("*.json"):
        names.add(p.stem)
    return sorted(names)


def get_palette(name: str, config_dir: Path) -> Palette:
    """Load a palette by name.

    Custom palettes in the config directory override built-ins.
    Unknown names fall back to gruvbox.
    """
    custom = palettes_dir(config_dir) / f"{name}.json"
    if custom.exists():
        try:
            return load_palette_file(custom)
        except ValueError:
            pass
    if name in BUILTIN_PALETTES:
        return BUILTIN_PALETTES[name]
    return BUILTIN_PALETTES["gruvbox"]
