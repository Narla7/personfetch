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


#: Path to the controlling terminal for queries (monkeypatched in tests).
_TTY_PATH = "/dev/tty"


def _tty_query(query: str, done, timeout: float = QUERY_TIMEOUT) -> bytes:
    """Write *query* to the terminal and read its response from the tty.

    Returns the raw bytes received (possibly empty). *done(buf)* decides
    when enough has arrived. Terminal settings are always restored.
    """
    try:
        import select
        import termios
        import tty
    except ImportError:  # non-POSIX (Windows): no query possible
        return b""
    try:
        tty_in = open(_TTY_PATH, "r+b", buffering=0)
    except OSError:
        return b""
    fd = tty_in.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        tty_in.close()
        return b""
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
            if done(buf):
                break
        return buf
    except (OSError, termios.error):
        return b""
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except termios.error:
            pass
        tty_in.close()


def _probe_support(timeout: float = QUERY_TIMEOUT) -> bool:
    """Ask the terminal if it speaks kitty graphics; False on any failure."""
    if not sys.stdout.isatty():
        return False
    # Query the status of a dummy image id. Terminals with graphics support
    # answer with an ESC_G response; anything else stays silent -> timeout.
    query = _maybe_wrap("\x1b_Gi=99,a=q\x1b\\")

    def done(buf: bytes) -> bool:
        return b"\x1b\\" in buf or b"\x07" in buf

    return b"\x1b_G" in _tty_query(query, done, timeout)


_cached_cell_size: tuple[int, int] | None | bool = None  # None=unknown, False=unavailable


def _cell_size(timeout: float = QUERY_TIMEOUT) -> tuple[int, int] | None:
    """Report the terminal cell size in pixels via CSI 16 t (cached)."""
    global _cached_cell_size
    if _cached_cell_size is None:
        import re as _re

        def done(buf: bytes) -> bool:
            return _re.search(rb"\x1b\[6;\d+;\d+t", buf) is not None

        m = _re.search(rb"\x1b\[6;(\d+);(\d+)t", _tty_query("\x1b[16t", done, timeout))
        _cached_cell_size = (int(m.group(2)), int(m.group(1))) if m else False
    return _cached_cell_size or None


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
    """Build the chunked transmit escape sequences for *data*.

    Mirrors kitty's own serializer: the first chunk carries the full
    control data, continuation chunks carry only ``m`` — with NO leading
    comma (``\\x1b_Gm=0;...``). A leading comma is tolerated by kitty
    itself but makes stricter terminals drop the whole transmission.
    """
    b64 = base64.b64encode(data).decode("ascii")
    out: list[str] = []
    first = True
    while b64:
        chunk, b64 = b64[:4096], b64[4096:]
        more = 1 if b64 else 0
        if first:
            out.append(_maybe_wrap(f"\x1b_G{control},m={more};{chunk}\x1b\\"))
            first = False
        else:
            out.append(_maybe_wrap(f"\x1b_Gm={more};{chunk}\x1b\\"))
    return "".join(out)


def transmit_png(path: Path | str, cols: int | None = None) -> str:
    """Transmit an image (``a=t``) and return display + transmit sequences.

    Two-step like ``kitten icat``: store with ``a=t`` (explicit pixel size
    ``s``/``v``, byte size ``S``, image id), then display with ``a=p``.
    The image is downscaled to display size and sent losslessly (PNG,
    full color — no tint/quantization). ``cols`` sets the display width
    in terminal columns (``c=``); the terminal preserves aspect ratio.
    ``q=2`` suppresses OK responses so they can't leak into shell input.
    Returns ``transmit + display``; display must be printed where the
    image should appear.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail(MAX_TRANSMIT_SIZE, Image.Resampling.LANCZOS)
        w, h = im.size
        import io as _io

        buf = _io.BytesIO()
        im.save(buf, format="PNG")
        payload = buf.getvalue()
    control = f"a=t,f=100,t=d,s={w},v={h},S={len(payload)},i=1,q=2"
    seq = _transmit_chunks(payload, control)
    display = f"a=p,i=1,q=2"
    if cols:
        display += f",c={cols}"
    return seq + _maybe_wrap(f"\x1b_G{display}\x1b\\")


def display_rows(path: Path | str, cols: int) -> int:
    """How many terminal rows the image will occupy at *cols* columns wide.

    Exact when the terminal reports its cell size (CSI 16 t): the image is
    scaled to ``cols`` cells wide with aspect preserved. Otherwise falls
    back to the classic ~1:2 cell aspect guess.
    """
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        if w == 0:
            return cols // 2
        import math as _math

        cell = _cell_size()
        if cell is not None:
            cw, ch = cell
            if cw > 0 and ch > 0:
                return max(1, _math.ceil(cols * cw * h / (w * ch)))
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

    Inline layout with no cursor gymnastics: save the cursor, display the
    image (it occupies R rows below the cursor), restore the cursor, then
    print each info line offset by (cols + gutter) columns. Everything
    flows from the current cursor position — never the top of the screen.
    If the terminal ignores graphics, the text still prints sanely at the
    cursor. Plain ASCII/half-block fallback lives in render.py.
    """
    seq = transmit_png(image_path, cols=cols)
    rows = display_rows(image_path, cols)
    out: list[str] = []
    out.append("\x1b7")  # DECSC: save cursor
    out.append(seq)
    out.append("\x1b8")  # DECRC: restore cursor to the card's first row
    right = cols + gutter
    for i, line in enumerate(info_lines):
        out.append("\r")
        out.append(f"\x1b[{right}C")
        out.append(line)
        out.append("\n")
    # Move the cursor below the image if it is taller than the text.
    for _ in range(max(0, rows - len(info_lines))):
        out.append("\n")
    return "".join(out)


def write_transmit(path: Path | str, cols: int | None = None) -> None:
    """Transmit + display an image on stdout (for debugging)."""
    sys.stdout.write("\x1b7" + transmit_png(path, cols=cols) + "\x1b8\n")
    sys.stdout.flush()
