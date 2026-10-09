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


def _build_logo(profile: dict, palette: list[tuple[int, int, int]] | None, logo_width: int) -> list[str]:
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


def render(profile: dict, width: int | None = None, mode: str = "ascii") -> str:
    """Render a profile as a fastfetch-style card.

    ``mode``: "ascii" (default — half-blocks, works everywhere) or "image"
    (whole card composed to one PNG and shown via kitty graphics; falls
    back to half-blocks if the terminal stays silent on the probe).
    """
    term_w, _ = shutil.get_terminal_size((80, 24))
    if width is None:
        width = term_w

    # Image path: single full-card PNG, no column alignment involved.
    # Failure (or terminal silence on the probe) falls through to ASCII.
    if mode == "image":
        from . import kitty as kitty_mod

        if kitty_mod.kitty_supported():
            try:
                return kitty_mod.kitty_full_card(
                    profile, cols=max(20, min(width, 80))
                )
            except Exception:
                pass
        else:
            import sys as _sys

            _sys.stderr.write(
                "personfetch: terminal ignored the graphics probe, "
                "falling back to ascii\n"
            )

    palette_name = profile.get("palette", "gruvbox")
    palette: list[tuple[int, int, int]] | None = (
        None if palette_name == "auto" else get_palette(palette_name, config_dir())
    )
    logo_width = max(4, profile.get("logo_width", 34))
    gutter = profile.get("gutter", 3)
    separator = profile.get("separator", ":")

    info_lines = []
    for field in profile.get("fields", []):
        label = field.get("label", "")
        value = field.get("value", "")
        color = field.get("color", "#ebdbb2")
        colored_label = ansi_fg(color) + label + "\033[0m"
        info_lines.append(f"{colored_label}{separator} {value}")

    logo = _build_logo(profile, palette, logo_width)
    actual_logo_width = max(image_mod.visible_len(line) for line in logo) if logo else 0

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
