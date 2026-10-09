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


def _build_logo(
    profile: dict,
    palette: list[tuple[int, int, int]] | None,
    logo_width: int,
    image_mode: str = "braille",
) -> list[str]:
    image_path = profile.get("image_path")
    if image_path and Path(image_path).exists():
        try:
            render_fn = (
                image_mod.portrait_from_path_braille
                if image_mode == "braille"
                else image_mod.portrait_from_path
            )
            return render_fn(
                Path(image_path),
                palette,
                target_width_cells=logo_width,
                dither=profile.get("dither", True),
            )
        except Exception as exc:
            return image_mod.fallback_logo() + [f"(image error: {exc})"]
    return image_mod.fallback_logo()


def render(profile: dict, width: int | None = None, mode: str = "auto") -> str:
    """Render a profile as a fastfetch-style card.

    ``mode``: "auto" (kitty graphics if the terminal supports it, else the
    profile's ``image_mode`` style), "kitty" (force), "braille" (force the
    2x-detailed braille renderer), "ascii" (force classic half-blocks).
    """
    term_w, _ = shutil.get_terminal_size((80, 24))
    if width is None:
        width = term_w

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

    # Kitty graphics path: full-color image transmitted over the protocol.
    from . import kitty as kitty_mod

    image_path = profile.get("image_path")
    if (
        mode in ("auto", "kitty")
        and image_path
        and Path(image_path).exists()
        and kitty_mod.supports_kitty(force="kitty" if mode == "kitty" else None)
    ):
        try:
            logo_rows = kitty_mod.display_rows(image_path, logo_width)
            centered = _vcenter(info_lines, logo_rows)
            return kitty_mod.kitty_card(
                image_path, centered, cols=logo_width, gutter=gutter
            )
        except (OSError, ValueError):
            pass

    image_mode = (
        "halfblock"
        if mode == "ascii"
        else "braille"
        if mode == "braille"
        else profile.get("image_mode", "braille")
    )

    logo = _build_logo(profile, palette, logo_width, image_mode=image_mode)
    actual_logo_width = max(image_mod.visible_len(line) for line in logo) if logo else 0

    info_width = max((image_mod.visible_len(line) for line in info_lines), default=0)

    # Shrink the logo until everything fits side-by-side.
    while actual_logo_width + gutter + info_width > width and logo_width > 10:
        logo_width -= 2
        logo = _build_logo(profile, palette, logo_width, image_mode=image_mode)
        actual_logo_width = max(image_mod.visible_len(line) for line in logo) if logo else 0
        info_width = max((image_mod.visible_len(line) for line in info_lines), default=0)

    lines = []
    right_lines = _vcenter(info_lines, max(len(logo), len(info_lines)))
    max_rows = max(len(logo), len(right_lines))
    for i in range(max_rows):
        left = logo[i] if i < len(logo) else " " * actual_logo_width
        right = right_lines[i] if i < len(right_lines) else ""
        left = pad_ansi(left, actual_logo_width)
        lines.append(left + " " * gutter + right)

    return "\n".join(lines)


def _vcenter(info_lines: list[str], height: int) -> list[str]:
    """Pad *info_lines* with blank lines so they sit vertically centered."""
    pad = max(0, (height - len(info_lines)) // 2)
    return [""] * pad + info_lines
