"""Convert an image into a retro ANSI half-block portrait.

The pipeline is intentionally soft + quantized: downscale with a smooth filter,
map to a limited palette, then render two pixels per terminal row with the
upper-half block character (▀). The result is exactly the blurry-retro vibe
we're aiming for.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from PIL import Image, ImageOps

from .palettes import Palette


HALF_BLOCK = "▀"
_RESET = "\033[0m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def supports_truecolor() -> bool:
    """Return True if the terminal advertises 24-bit color support."""
    term = os.environ.get("COLORTERM", "")
    return "truecolor" in term or "24bit" in term


def visible_len(s: str) -> int:
    """Visible length of a string that may contain ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Convert an RGB triple to the closest xterm-256 color index."""
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + ((r - 8) // 10)
    r_idx = 0 if r < 48 else min(5, (r - 35) // 40)
    g_idx = 0 if g < 48 else min(5, (g - 35) // 40)
    b_idx = 0 if b < 48 else min(5, (b - 35) // 40)
    return 16 + 36 * r_idx + 6 * g_idx + b_idx


def _color_seq(plane: str, color: tuple[int, int, int]) -> str:
    """Return an ANSI color sequence for a plane ('38' fg or '48' bg)."""
    if supports_truecolor():
        return f"\033[{plane};2;{color[0]};{color[1]};{color[2]}m"
    n = rgb_to_ansi256(*color)
    return f"\033[{plane};5;{n}m"


def _build_palette_image(palette: Palette) -> Image.Image:
    """Build a Pillow palette image from a list of RGB colors."""
    flat = []
    for color in palette:
        flat.extend(color)
    # Pad to 256 colors * 3 channels (required by Pillow).
    while len(flat) < 768:
        flat.extend((0, 0, 0))
    palette_img = Image.new("P", (1, 1))
    palette_img.putpalette(flat[:768])
    return palette_img


def quantize_to_palette(
    image: Image.Image, palette: Palette, dither: bool = True
) -> Image.Image:
    """Quantize an RGB image to the given palette."""
    palette_img = _build_palette_image(palette)
    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    return image.quantize(palette=palette_img, dither=dither_mode).convert("RGB")


def _ensure_even_height(image: Image.Image) -> Image.Image:
    """Duplicate the last row if the image has an odd number of rows."""
    width, height = image.size
    if height % 2 == 0:
        return image
    new = Image.new("RGB", (width, height + 1), (0, 0, 0))
    new.paste(image, (0, 0))
    new.paste(image.crop((0, height - 1, width, height)), (0, height))
    return new


def _render_halfblocks(image: Image.Image) -> list[str]:
    """Render a quantized RGB image as ANSI half-block lines."""
    image = _ensure_even_height(image)
    width, height = image.size
    pixels = image.load()
    lines: list[str] = []
    for y in range(0, height, 2):
        parts: list[str] = []
        last_fg: tuple[int, int, int] | None = None
        last_bg: tuple[int, int, int] | None = None
        for x in range(width):
            top = pixels[x, y]
            bottom = pixels[x, y + 1]
            if top != last_fg:
                parts.append(_color_seq("38", top))
                last_fg = top
            if bottom != last_bg:
                parts.append(_color_seq("48", bottom))
                last_bg = bottom
            parts.append(HALF_BLOCK)
        lines.append("".join(parts) + _RESET)
    return lines


def portrait_from_path(
    path: Path | str,
    palette: Palette,
    target_width_cells: int = 34,
    dither: bool = True,
) -> list[str]:
    """Load an image and convert it to a retro ANSI half-block portrait."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")

        orig_w, orig_h = im.size
        if orig_w == 0 or orig_h == 0:
            raise ValueError("Image has zero dimension")

        # Each terminal cell is one character wide and roughly two pixels tall.
        # Using the upper-half block, one row covers two image pixels, so the
        # rendered aspect is close to the original.
        target_w = max(1, target_width_cells)
        target_h = max(2, int(round(orig_h * target_w / orig_w)))
        if target_h % 2 == 1:
            target_h += 1

        # Smooth downscale = the requested blurry-retro look.
        im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
        im = quantize_to_palette(im, palette, dither=dither)
        return _render_halfblocks(im)


def fallback_logo() -> list[str]:
    """A friendly placeholder face shown when no portrait image is set."""
    return [
        "   ▄▄▄▄▄▄   ",
        " ▄█████████▄ ",
        "███▀▀███▀▀███",
        "███    █   ██",
        "███▄  ▄█▄▄███",
        " ▀█████████▀ ",
        "   ▀▀▀▀▀▀▀   ",
    ]
