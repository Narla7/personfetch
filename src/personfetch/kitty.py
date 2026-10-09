"""Kitty graphics protocol support.

Strategy: try kitty first, fall back to half-blocks on failure. Whether the
terminal speaks the protocol is determined by *asking it* — a graphics
query is sent and only an actual protocol response enables kitty rendering.
No TERM / environment-variable guessing.
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

#: How long to wait for the terminal's query response before giving up.
QUERY_TIMEOUT = 0.1
#: Transmitted images are downscaled to fit this box (full-res photos would
#: otherwise dump megabytes of base64 at the terminal).
MAX_TRANSMIT_SIZE = (1280, 1280)

_cached_support: bool | None = None


def _tmux_wrap(s: str) -> str:
    """Wrap an escape sequence in tmux passthrough (same as kitten icat)."""
    return "\x1bPtmux;" + s.replace("\x1b", "\x1b\x1b") + "\x1b\\"


def _maybe_wrap(s: str) -> str:
    if os.environ.get("TMUX"):
        return _tmux_wrap(s)
    return s


def _probe_support(timeout: float = QUERY_TIMEOUT) -> bool:
    """Ask the terminal if it speaks kitty graphics; False on any failure."""
    if not sys.stdout.isatty():
        return False
    try:
        import select
        import termios
        import tty
    except ImportError:  # non-POSIX (Windows): no query possible
        return False
    try:
        tty_in = open("/dev/tty", "r+b", buffering=0)
    except OSError:
        return False
    fd = tty_in.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        tty_in.close()
        return False
    # Query the status of a dummy image id. Terminals with graphics support
    # answer with an ESC_G response; anything else stays silent -> timeout.
    query = _maybe_wrap("\x1b_Gi=99,a=q\x1b\\")
    try:
        tty.setraw(fd)
        sys.stdout.write(query)
        sys.stdout.flush()
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            remaining = deadline - time.time()
            r, _, _ = select.select([fd], [], [], remaining)
            if not r:
                break
            try:
                chunk = os.read(fd, 1024)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if b"\x1b\\" in buf or b"\x07" in buf:
                break
        return b"\x1b_G" in buf
    except (OSError, termios.error):
        return False
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except termios.error:
            pass
        tty_in.close()


def kitty_supported(force: str | None = None) -> bool:
    """Return True if kitty graphics should be attempted.

    ``force``: "kitty" always tries (skips the probe), "ascii" never does.
    Otherwise the terminal is probed once per process (cached); silence or
    any error means half-block fallback. Piped output never uses kitty.
    """
    global _cached_support
    override = os.environ.get("PERSONFETCH_KITTY", "").lower()
    if override in ("1", "true", "yes", "kitty"):
        return True
    if override in ("0", "false", "no", "ascii"):
        return False
    if force == "kitty":
        return True
    if force == "ascii":
        return False
    if _cached_support is None:
        _cached_support = _probe_support()
    return _cached_support


def _transmit_chunks(data: bytes, control: str) -> str:
    """Build the chunked ``a=T`` transmit escape sequence for *data*."""
    b64 = base64.b64encode(data).decode("ascii")
    out: list[str] = []
    first = True
    while b64:
        chunk, b64 = b64[:4096], b64[4096:]
        more = 1 if b64 else 0
        prefix = control if first else ""
        out.append(_maybe_wrap(f"\x1b_G{prefix},m={more};{chunk}\x1b\\"))
        first = False
        control = ""
    return "".join(out)


def transmit_png(path: Path | str, cols: int | None = None) -> str:
    """Read an image file and return the kitty transmit escape sequence.

    The image is downscaled to display size and sent losslessly (PNG,
    full color — no tint/quantization). ``cols`` sets the display width
    in terminal columns (``c=``); the terminal preserves aspect ratio.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail(MAX_TRANSMIT_SIZE, Image.Resampling.LANCZOS)
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
    out: list[str] = []
    out.append(seq + "\n")
    # Cursor is now below the image; climb back to its first row.
    out.append(f"\x1b[{total}A")
    right = cols + gutter
    for i in range(total):
        out.append(f"\x1b[{right}C")
        if i < len(info_lines):
            out.append(info_lines[i])
        out.append("\r\n")
    return "".join(out)


def write_transmit(path: Path | str, cols: int | None = None) -> None:
    """Transmit an image directly to stdout (for debugging)."""
    sys.stdout.write(transmit_png(path, cols=cols))
    sys.stdout.flush()
