"""Kitty graphics protocol support.

Renders the portrait at full color (no palette quantization / no tint) via
the Kitty graphics protocol, falling back to ANSI half-blocks elsewhere.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps


def kitty_supported(force: str | None = None) -> bool:
    """Return True if the terminal likely speaks the Kitty graphics protocol.

    ``force`` overrides detection: "kitty" -> True, "ascii" -> False.
    Auto-detect order:
      1. PERSONFETCH_KITTY=1/0 explicit override
      2. ``force`` argument
      3. stdout must be a TTY (never dump graphics escapes into a pipe)
      4. $KITTY_WINDOW_ID (set by kitty itself, per window) or
         $TERM == xterm-kitty.

    Note: $KITTY_PID is deliberately NOT trusted — it leaks into child
    environments (other terminals, pipes, tmux) where stdout doesn't speak
    the protocol, which used to blank the output entirely.
    """
    override = os.environ.get("PERSONFETCH_KITTY", "").lower()
    if override in ("1", "true", "yes", "kitty"):
        return True
    if override in ("0", "false", "no", "ascii"):
        return False
    if force == "kitty":
        return True
    if force == "ascii":
        return False
    if not sys.stdout.isatty():
        return False
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    if os.environ.get("TERM", "").lower() == "xterm-kitty":
        return True
    return False


def _transmit_chunks(data: bytes, control: str) -> str:
    """Build the chunked ``a=T`` transmit escape sequence for *data*."""
    b64 = base64.b64encode(data).decode("ascii")
    out: list[str] = []
    first = True
    while b64:
        chunk, b64 = b64[:4096], b64[4096:]
        more = 1 if b64 else 0
        prefix = control if first else ""
        out.append(f"\x1b_G{prefix},m={more};{chunk}\x1b\\")
        first = False
        control = ""
    return "".join(out)


def transmit_png(path: Path | str, cols: int | None = None) -> str:
    """Read an image file and return the kitty transmit escape sequence.

    The image is sent losslessly (PNG, full color — no tint/quantization).
    ``cols`` sets the display width in terminal columns (``c=``); the
    terminal preserves aspect ratio for the height.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        import io as _io

        buf = _io.BytesIO()
        im.save(buf, format="PNG")
        payload = buf.getvalue()
    control = "a=T,f=100"
    if cols:
        control += f",c={cols}"
    return _transmit_chunks(payload, control)


def display_rows(path: Path | str, cols: int) -> int:
    """Estimate how many terminal rows a kitty image will occupy.

    Assumes the classic ~1:2 cell aspect ratio (char ~twice as tall as wide).
    """
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        if w == 0:
            return cols // 2
        return max(1, round(cols * h / w / 2))
    except Exception:
        return cols // 2


def kitty_card(
    image_path: Path | str,
    info_lines: list[str],
    cols: int = 34,
    gutter: int = 3,
) -> str:
    """Render a side-by-side card: kitty image left, info lines right.

    Technique: transmit the image (occupies R rows), move the cursor back
    up R rows, then print each info line offset by (cols + gutter) columns.
    After the last row the cursor rests below the image. Plain ASCII/half-
    block fallback lives in render.py — this function is kitty-only.
    """
    seq = transmit_png(image_path, cols=cols)
    rows = display_rows(image_path, cols)
    total = max(rows, len(info_lines))
    pad = " " * 0  # offsets are done with cursor-forward escapes, not spaces
    _ = pad
    out: list[str] = []
    out.append(seq + "\n")
    # Cursor is now below the image; climb back to its first row.
    out.append(f"\x1b[{total}A")
    right = cols + gutter
    for i in range(total):
        out.append(f"\x1b[{right}C")
        if i < len(info_lines):
            out.append(info_lines[i])
        # Move to start of next line without scrolling weirdness.
        out.append("\r\n" if i < total - 1 else "\r\n")
    return "".join(out)


def write_transmit(path: Path | str, cols: int | None = None) -> None:
    """Transmit an image directly to stdout (for debugging)."""
    sys.stdout.write(transmit_png(path, cols=cols))
    sys.stdout.flush()
