"""Render the profile card to a shareable PNG (gravatar/monkeytype-style)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

BG = (30, 30, 46)
FG = (205, 214, 244)
MUTED = (147, 153, 178)
ACCENT = (203, 166, 247)
PAD = 48
AVATAR_SIZE = 320
LINE_GAP = 14
TITLE_SIZE = 40
BODY_SIZE = 28


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rounded(img: Image.Image, radius: int = 48) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


def export_png(profile: dict, dest: Path | str, width: int = 1200) -> Path:
    """Render the card to *dest* and return its path."""
    dest = Path(dest).expanduser()
    fields = profile.get("fields", [])
    separator = profile.get("separator", ":")

    title_f = _font(TITLE_SIZE)
    body_f = _font(BODY_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    name = next((f.get("value", "") for f in fields if f.get("label") == "name"), "personfetch")

    def text_w(s: str, f: ImageFont.ImageFont) -> int:
        box = probe.textbbox((0, 0), s, font=f)
        return box[2] - box[0]

    line_h = BODY_SIZE + LINE_GAP
    left_w = AVATAR_SIZE + PAD * 2
    # Measure the widest info line.
    info_w = text_w(name, title_f)
    for f in fields:
        info_w = max(info_w, text_w(f"{f.get('label', '')}{separator} {f.get('value', '')}", body_f))
    card_w = min(width, left_w + info_w + PAD * 2)
    card_h = PAD * 2 + TITLE_SIZE + LINE_GAP + max(1, len(fields)) * line_h + 40

    card = Image.new("RGB", (card_w, card_h), BG)
    d = ImageDraw.Draw(card)

    # Avatar block.
    ax, ay = PAD, PAD
    avatar: Image.Image | None = None
    image_path = profile.get("image_path")
    if image_path and Path(image_path).exists():
        try:
            with Image.open(image_path) as im:
                avatar = ImageOps.exif_transpose(im).convert("RGB")
                avatar = ImageOps.fit(avatar, (AVATAR_SIZE, AVATAR_SIZE))
        except Exception:
            avatar = None
    if avatar is None:
        avatar = Image.new("RGB", (AVATAR_SIZE, AVATAR_SIZE), (24, 24, 37))
        da = ImageDraw.Draw(avatar)
        da.text((AVATAR_SIZE // 2 - 40, AVATAR_SIZE // 2 - 30), ":)", font=_font(72), fill=MUTED)
    card.paste(_rounded(avatar.convert("RGBA")), (ax, ay), _rounded(avatar.convert("RGBA")))

    # Text block.
    tx = left_w + PAD
    ty = PAD
    d.text((tx, ty), name, font=title_f, fill=ACCENT)
    ty += TITLE_SIZE + LINE_GAP + 8
    for f in fields:
        if f.get("label", "") == "name":
            continue
        label = f.get("label", "")
        value = f.get("value", "")
        try:
            color = _hex_to_rgb(f.get("color", "#cdd6f4"))
        except (ValueError, AttributeError):
            color = FG
        d.text((tx, ty), f"{label}{separator} ", font=body_f, fill=color)
        lx = tx + text_w(f"{label}{separator} ", body_f)
        d.text((lx, ty), value, font=body_f, fill=FG)
        ty += line_h

    handle = next((f.get("value", "") for f in fields if f.get("label", "") in ("github", "twitter")), "")
    if handle:
        d.text((tx, card_h - PAD - 10), str(handle), font=body_f, fill=MUTED)

    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest, format="PNG")
    return dest
