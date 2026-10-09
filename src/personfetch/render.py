"""Render the profile card: portrait + fastfetch-style keys."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import image as image_mod
from .palettes import get_palette
from .profile import config_dir


def hex_to_rgb(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def ansi_fg(hexcolor: str) -> str:
    """ANSI foreground sequence for a hex color (truecolor or 256 fallback)."""
    r, g, b = hex_to_rgb(hexcolor)
    if image_mod.supports_truecolor():
        return f"\033[38;2;{r};{g};{b}m"
    n = image_mod.rgb_to_ansi256(r, g, b)
    return f"\033[38;5;{n}m"


def pad_ansi(line: str, width: int) -> str:
    """Right-pad a string, ignoring ANSI escape codes when measuring width."""
    pad = width - image_mod.visible_len(line)
    if pad > 0:
        return line + " " * pad
    return line


def _build_logo(profile: dict, palette: list[tuple[int, int, int]], logo_width: int) -> list[str]:
    image_path = profile.get("image_path")
    if image_path and Path(image_path).exists():
        try:
            return image_mod.portrait_from_path(
                Path(image_path),
                palette,
                target_width_cells=logo_width,
                dither=profile.get("dither", True),
            )
        except Exception as exc:
            return image_mod.fallback_logo() + [f"(image error: {exc})"]
    return image_mod.fallback_logo()


def render(profile: dict, width: int | None = None) -> str:
    """Render a profile as a fastfetch-style card."""
    term_w, _ = shutil.get_terminal_size((80, 24))
    if width is None:
        width = term_w

    palette_name = profile.get("palette", "gruvbox")
    palette = get_palette(palette_name, config_dir())
    logo_width = max(4, profile.get("logo_width", 34))
    gutter = profile.get("gutter", 3)
    separator = profile.get("separator", ":")

    logo = _build_logo(profile, palette, logo_width)
    actual_logo_width = max(image_mod.visible_len(line) for line in logo) if logo else 0

    info_lines = []
    for field in profile.get("fields", []):
        label = field.get("label", "")
        value = field.get("value", "")
        color = field.get("color", "#ebdbb2")
        colored_label = ansi_fg(color) + label + "\033[0m"
        info_lines.append(f"{colored_label}{separator} {value}")

    info_width = max((image_mod.visible_len(line) for line in info_lines), default=0)

    # Shrink the logo until everything fits side-by-side.
    while actual_logo_width + gutter + info_width > width and logo_width > 10:
        logo_width -= 2
        logo = _build_logo(profile, palette, logo_width)
        actual_logo_width = max(image_mod.visible_len(line) for line in logo) if logo else 0
        info_width = max((image_mod.visible_len(line) for line in info_lines), default=0)

    lines = []
    max_rows = max(len(logo), len(info_lines))
    for i in range(max_rows):
        left = logo[i] if i < len(logo) else " " * actual_logo_width
        right = info_lines[i] if i < len(info_lines) else ""
        left = pad_ansi(left, actual_logo_width)
        lines.append(left + " " * gutter + right)

    return "\n".join(lines)
