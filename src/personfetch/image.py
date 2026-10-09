"""Convert an image into a retro ANSI half-block portrait.

The pipeline downscale with a sharp filter, apply an unsharp mask,
map to a limited palette, then render two pixels per terminal row with the
upper-half block character (▀).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

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


def _load_image(path: Path | str) -> Image.Image:
    """Open *path*, apply EXIF rotation, and return as RGB."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return im


def _prepare(
    im: Image.Image, target_w: int, target_h: int
) -> Image.Image:
    """Downscale (LANCZOS) + sharpen: keeps edges crisp instead of mushy."""
    im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return im.filter(
        ImageFilter.UnsharpMask(radius=1.5, percent=220, threshold=2)
    )


def _quantize(
    im: Image.Image, palette: Palette | None, dither: bool
) -> Image.Image:
    if palette is None:
        # Adaptive quantization: keep up to 256 of the photo's own tones,
        # maximising detail instead of forcing a fixed theme palette.
        dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
        return im.quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=dither_mode
        ).convert("RGB")
    return quantize_to_palette(im, palette, dither=dither)


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
    palette: Palette | None,
    target_width_cells: int = 44,
    dither: bool = True,
) -> list[str]:
    """Load an image and convert it to a retro ANSI half-block portrait."""
    im = _load_image(path)
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
    im = _prepare(im, target_w, target_h)
    im = _quantize(im, palette, dither)
    return _render_halfblocks(im)


# Braille pattern bitmap: bit i = dot number (1-8), stored column-major at
# position (x, y) in the 2x4 cell matrix, i.e. bits 0..3 down the left
# column and bits 4..7 down the right.
_BRAILLE_BITS = {
    (x, y): 1 << (x * 4 + y) for x in range(2) for y in range(4)
}
BRAILLE_BASE = 0x2800


def _ensure_block_height(image: Image.Image, block: int) -> Image.Image:
    """Pad the image height by repeating the last row until it's a multiple of *block*."""
    width, height = image.size
    remainder = height % block
    if remainder == 0:
        return image
    new = Image.new("RGB", (width, height + block - remainder), (0, 0, 0))
    new.paste(image, (0, 0))
    new.paste(image.crop((0, height - 1, width, height)), (0, height))
    return new


def _render_braille(image: Image.Image) -> list[str]:
    """Render a quantized RGB image as 2x4 subpixels per braille cell.

    Each cell picks a background (dominant color of its 2x4 pixel block) and
    a foreground (dominant of the remaining pixels); pixels matching the
    foreground become lit braille dots. Solid blocks render as plain spaces
    with an exact background color. This yields 4x the pixel coverage of the
    half-block renderer at the same cell count.
    """
    from collections import Counter

    image = _ensure_block_height(image, 4)
    width, height = image.size
    pixels = image.load()
    cells_w = width // 2
    cells_h = height // 4
    lines: list[str] = []
    for cy in range(cells_h):
        parts: list[str] = []
        last: str | None = None
        for cx in range(cells_w):
            samples = [
                pixels[cx * 2 + dx, cy * 4 + dy]
                for dy in range(4)
                for dx in range(2)
            ]
            counts = Counter(samples)
            bg = counts.most_common(1)[0][0]
            lit = [c for c, n in counts.items() if c != bg]
            if not lit:
                seq = _color_seq("48", bg) + " "
            else:
                fg = Counter(lit).most_common(1)[0][0]
                mask = 0
                for sample, bit in _BRAILLE_BITS.items():
                    if pixels[cx * 2 + sample[0], cy * 4 + sample[1]] == fg:
                        mask |= bit
                seq = (
                    _color_seq("38", fg)
                    + _color_seq("48", bg)
                    + chr(BRAILLE_BASE + mask)
                )
            if seq != last:
                parts.append(seq)
                last = seq
        lines.append("".join(parts) + _RESET)
    return lines


def portrait_from_path_braille(
    path: Path | str,
    palette: Palette | None,
    target_width_cells: int = 44,
    dither: bool = True,
) -> list[str]:
    """Load an image and convert it to a detailed ANSI braille portrait.

    Every cell holds 2x4 pixels (double the half-block renderer in both
    directions), quantized to the given palette (or adaptively when
    ``palette`` is None).
    """
    im = _load_image(path)
    orig_w, orig_h = im.size
    if orig_w == 0 or orig_h == 0:
        raise ValueError("Image has zero dimension")

    target_w = max(2, target_width_cells * 2)
    target_h = max(4, round(orig_h * target_w / orig_w))
    if target_h % 4:
        target_h += 4 - (target_h % 4)
    im = _prepare(im, target_w, target_h)
    im = _quantize(im, palette, dither)
    return _render_braille(im)


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
