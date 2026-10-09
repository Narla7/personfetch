"""Kitty terminal graphics protocol support.

Renders the portrait at full color by transmitting it to the terminal with
the kitty graphics protocol (https://sw.kovidgoyal.net/kitty/graphics-protocol/).
Support is determined by *probing* the terminal: we send a graphics query
and only enable this mode if it actually answers. No env guessing.
"""

from __future__ import annotations

import base64
import io
import os
import select
import sys
import termios
import time
import tty
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

QUERY_TIMEOUT = 0.15
_CHUNK = 4096
_cached_support: bool | None = None


def _tmux_wrap(s: str) -> str:
    return "\x1bPtmux;" + s.replace("\x1b", "\x1b\x1b") + "\x1b\\"


def _maybe_wrap(s: str) -> str:
    if os.environ.get("TMUX"):
        return _tmux_wrap(s)
    return s


def _read_response(fd: int, deadline: float) -> bytes:
    buf = b""
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if b"\x1b\\" in buf or b"\x07" in buf:
            break
    return buf


def _query(query: str, timeout: float = QUERY_TIMEOUT) -> bytes:
    """Write *query* to the tty and return the terminal's raw response."""
    fd = os.open("/dev/tty", os.O_RDWR)
    try:
        try:
            old = termios.tcgetattr(fd)
        except termios.error:
            return b""
        try:
            tty.setraw(fd)
            os.write(fd, query.encode())
            return _read_response(fd, time.time() + timeout)
        except OSError:
            return b""
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except termios.error:
                pass
    finally:
        os.close(fd)


def _cell_size() -> tuple[int, int] | None:
    """Ask the terminal for its cell size in pixels via CSI 16 t."""
    resp = _query("\x1b[16t")
    for line in resp.split(b"\x1b["):
        if line.startswith(b"6;"):
            tail = line[2:].split(b"t")[0].split(b";")
            if len(tail) == 2 and tail[0].isdigit() and tail[1].isdigit():
                h, w = int(tail[0]), int(tail[1])
                if w > 0 and h > 0:
                    return (w, h)
    return None


def _probe_support() -> bool:
    if not sys.stdout.isatty():
        return False
    try:
        if not _query("\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24\x1b\\").startswith(b"\x1b_G"):
            return False
    except OSError:
        return False
    return True


def supports_kitty(force: str | None = None) -> bool:
    """Return True if kitty graphics should be used.

    ``force="kitty"`` always enables, ``"ascii"`` never. Otherwise the
    terminal is probed once per process; silence or errors mean fallback.
    """
    global _cached_support
    override = os.environ.get("PERSONFETCH_KITTY", "").lower()
    if override in ("1", "true", "yes"):
        return True
    if override in ("0", "false", "no"):
        return False
    if force == "kitty":
        return True
    if force == "ascii":
        return False
    if _cached_support is None:
        try:
            _cached_support = _probe_support()
        except (OSError, termios.error, ValueError):
            _cached_support = False
    return _cached_support


def prepare_image(path: Path | str, width_px: int) -> tuple[bytes, int, int]:
    """Return (PNG bytes, w, h) for *path* sized to *width_px* pixels wide.

    Keeps the source aspect ratio; the same sharpen treatment as the
    half-block pipeline so portrait edges stay crisp.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        orig_w, orig_h = im.size
        if orig_w <= 0 or orig_h <= 0:
            raise ValueError("Image has zero dimension")
        width_px = max(1, width_px)
        h = max(1, round(orig_h * width_px / orig_w))
        im = im.resize((width_px, h), Image.Resampling.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=220, threshold=2))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue(), width_px, h


def _transmit(data: bytes, w: int, h: int, cols: int, rows: int, ident: int) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    parts: list[str] = []
    first = True
    while b64:
        chunk, b64 = b64[:_CHUNK], b64[_CHUNK:]
        more = 1 if b64 else 0
        control = f"a=T,f=100,q=1,i={ident},s={w},v={h},c={cols},r={rows},m={more}"
        if not first:
            control = f"q=1,m={more}"
        parts.append(_maybe_wrap(f"\x1b_G{control};{chunk}\x1b\\"))
        first = False
    return "".join(parts)


def kitty_card(
    image_path: Path | str,
    info_lines: list[str],
    cols: int = 44,
    gutter: int = 3,
) -> str:
    """Build the escape-sequence card: kitty image left, info lines right.

    The transmitted image is laid out over ``r=`` rows at the cursor, the
    cursor is walked back up to its top row, and each info line is written
    offset by ``cols + gutter`` columns.
    """
    cell = _cell_size()
    cell_w, cell_h = cell if cell else (10, 20)
    payload, w, h = prepare_image(image_path, cols * cell_w)
    rows = max(1, -(-h // cell_h))
    ident = int(time.time() * 10) % 9000 + 100

    out: list[str] = [_transmit(payload, w, h, cols, rows, ident)]
    out.append("\x1b[9999D\x1b[F" if rows == 1 else f"\x1b[{rows}A")
    offset = cols + gutter
    total = max(rows, len(info_lines))
    for i in range(total):
        out.append(f"\x1b[{offset}C")
        if i < len(info_lines):
            out.append(info_lines[i])
        out.append("\n" if i < total - 1 else "")
    return "".join(out)
