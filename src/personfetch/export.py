"""Render the profile card to an image with terminal fidelity.

Same grid as the terminal card: monospace JetBrains Mono, colored
``label: value`` lines, square avatar sized in cells, transparent
background, no chrome. Used both for ``personfetch export`` and for
``personfetch --image`` (single-PNG inline display).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FG = (205, 214, 244)  # value color (terminal foreground stand-in)
TRANSPARENT = (0, 0, 0, 0)

_FONT_FAMILIES = [
    "JetBrains Mono",
    "JetBrainsMono Nerd Font Mono",
    "JetBrainsMono NFM Mono",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "monospace",
]


def _is_mono(font: ImageFont.FreeTypeFont) -> bool:
    try:
        return abs(font.getlength("i") - font.getlength("W")) < 1.0
    except Exception:
        return False


def _find_mono_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best monospace font available, JetBrains Mono first."""
    if shutil.which("fc-match"):
        for family in _FONT_FAMILIES:
            try:
                proc = subprocess.run(
                    ["fc-match", family, "--format=%{file}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                path = proc.stdout.strip()
                if path and os.path.exists(path):
                    font = ImageFont.truetype(path, size)
                    if _is_mono(font):
                        return font
            except Exception:
                continue
    for name in ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            if _is_mono(font):
                return font
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _avatar_box(profile: dict) -> tuple[Image.Image, int, int] | None:
    """Return (avatar, width, height) or None when no portrait is set."""
    image_path = profile.get("image_path")
    if not image_path or not Path(image_path).exists():
        return None
    try:
        with Image.open(image_path) as im:
            avatar = ImageOps.exif_transpose(im).convert("RGB")
            w, h = avatar.size
            if w == 0 or h == 0:
                return None
            return avatar, w, h
    except Exception:
        return None


def render_card_image(
    profile: dict, font_size: int = 30, max_cols: int | None = None
) -> tuple[Image.Image, int, int]:
    """Compose the card. Returns (image, display_cols, display_rows).

    Layout is computed in terminal cells so the PNG maps 1:1 onto the
    grid when displayed ``cols`` wide: one column = one character advance,
    one row = one line height. Avatar is top-aligned like the ASCII logo.
    """
    font = _find_mono_font(font_size)
    try:
        advance = font.getlength("n")
    except Exception:
        advance = font_size * 0.6
    pxc = max(1, int(round(advance)))
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = font_size, font_size // 4
    lh = ascent + descent + 2  # line height: tight, terminal-like

    separator = profile.get("separator", ":")
    fields = profile.get("fields", [])
    label_texts = [f"{f.get('label', '')}{separator} " for f in fields]
    value_texts = [f.get("value", "") for f in fields]
    text_w = 0
    for lab, val in zip(label_texts, value_texts):
        try:
            text_w = max(text_w, font.getlength(lab + val))
        except Exception:
            pass
    text_w = int(text_w) + 1

    avatar_info = _avatar_box(profile)
    logo_cells = profile.get("logo_width", 44)
    gutter_cells = profile.get("gutter", 3)
    if avatar_info is None:
        logo_cells, gutter_cells = 0, 0
    else:
        text_cells = text_w / pxc
        if max_cols:
            while logo_cells > 10 and logo_cells + gutter_cells + text_cells > max_cols:
                logo_cells -= 2

    text_rows = len(fields)

    avatar_rows = 0
    avatar: Image.Image | None = None
    logo_w_px = 0
    if avatar_info is not None and logo_cells > 0:
        src, sw, sh = avatar_info
        if text_rows > 0:
            # Contain-fit within (logo width × text height): no distortion,
            # no dead rows, top-aligned like the ASCII logo.
            box_w = logo_cells * pxc
            box_h = text_rows * lh
            scale = min(box_w / sw, box_h / sh)
            aw, ah = max(1, round(sw * scale)), max(1, round(sh * scale))
            avatar = src.resize((aw, ah), Image.Resampling.LANCZOS)
            avatar_rows = max(1, round(ah / lh))
            logo_w_px = aw
        else:
            logo_w_px = logo_cells * pxc
            avatar_rows = max(1, round(logo_w_px * sh / (sw * lh)))
            avatar = src.resize(
                (logo_w_px, avatar_rows * lh), Image.Resampling.LANCZOS
            )

    card_rows = max(avatar_rows, text_rows, 1)
    gutter_px = gutter_cells * pxc if avatar is not None else 0
    if avatar is None:
        logo_w_px = 0
    pad = 4
    card_w = pad * 2 + logo_w_px + gutter_px + text_w
    card_h = pad * 2 + card_rows * lh

    img = Image.new("RGBA", (card_w, card_h), TRANSPARENT)
    if avatar is not None:
        img.paste(avatar, (pad, pad))

    d = ImageDraw.Draw(img)
    tx = pad + logo_w_px + gutter_px
    for i, (lab, val) in enumerate(zip(label_texts, value_texts)):
        y = pad + i * lh
        try:
            color = _hex_to_rgb(fields[i].get("color", "#cdd6f4"))
        except (ValueError, AttributeError):
            color = FG
        d.text((tx, y), lab, font=font, fill=color)
        try:
            lx = tx + font.getlength(lab)
        except Exception:
            lx = tx
        d.text((lx, y), val, font=font, fill=FG)

    import math as _math

    return img, _math.ceil(card_w / pxc), _math.ceil(card_h / lh)


def export_png(profile: dict, dest: Path | str, font_size: int = 30) -> Path:
    """Render the card to *dest* and return its path."""
    dest = Path(dest).expanduser()
    img, _, _ = render_card_image(profile, font_size=font_size)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")
    return dest
