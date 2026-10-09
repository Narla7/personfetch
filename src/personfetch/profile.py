"""Profile persistence and defaults."""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path

from .palettes import ensure_builtin_palette_files


DEFAULT_LOGO_WIDTH = 44
DEFAULT_GUTTER = 3
DEFAULT_PALETTE = "gruvbox"
DEFAULT_DITHER = True
DEFAULT_SEPARATOR = ":"


def config_dir() -> Path:
    """Return the personfetch config directory (XDG-compliant)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "personfetch"
    return Path.home() / ".config" / "personfetch"


def ensure_config() -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    ensure_builtin_palette_files(d)
    return d


def profile_path() -> Path:
    return ensure_config() / "profile.json"


def avatar_path() -> Path:
    return ensure_config() / "avatar.png"


def detect_os() -> str:
    """Best-effort OS detection (fun fastfetch-style easter egg)."""
    system = platform.system()
    if system == "Linux":
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return system


def default_profile() -> dict:
    """A starter profile so the first run is never empty.

    Ships with a wide range of fields pre-filled (all editable/removable)
    so a fresh install already looks like a real bio card.
    """
    return {
        "version": 1,
        "image_path": None,
        "palette": DEFAULT_PALETTE,
        "logo_width": DEFAULT_LOGO_WIDTH,
        "gutter": DEFAULT_GUTTER,
        "dither": DEFAULT_DITHER,
        "separator": DEFAULT_SEPARATOR,
        "fields": [
            {"label": "name", "value": "Narla", "color": "#fabd2f"},
            {"label": "pronouns", "value": "he/him", "color": "#8ec07c"},
            {"label": "os", "value": detect_os(), "color": "#83a598"},
            {"label": "github", "value": "github.com/Narla7", "color": "#d3869b"},
            {"label": "twitter", "value": "@narla7", "color": "#83a598"},
            {"label": "company", "value": "acme", "color": "#fe8019"},
            {"label": "location", "value": "india", "color": "#b8bb26"},
            {"label": "bio", "value": "fastfetch, but for people", "color": "#ebdbb2"},
            {"label": "interests", "value": "linux, code, music", "color": "#d3869b"},
        ],
    }


def load_profile() -> dict:
    p = profile_path()
    if not p.exists():
        profile = default_profile()
        save_profile(profile)
        return profile

    with p.open("r", encoding="utf-8") as f:
        profile = json.load(f)

    # Tolerate / migrate older profiles.
    profile.setdefault("version", 1)
    profile.setdefault("image_path", None)
    profile.setdefault("palette", DEFAULT_PALETTE)
    profile.setdefault("logo_width", DEFAULT_LOGO_WIDTH)
    profile.setdefault("gutter", DEFAULT_GUTTER)
    profile.setdefault("dither", DEFAULT_DITHER)
    profile.setdefault("separator", DEFAULT_SEPARATOR)
    profile.setdefault("fields", [])
    return profile


def save_profile(profile: dict) -> None:
    p = profile_path()
    ensure_config()
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def find_field_index(profile: dict, label: str) -> int:
    label_lower = label.lower()
    for i, field in enumerate(profile.get("fields", [])):
        if field.get("label", "").lower() == label_lower:
            return i
    return -1


def _next_color(fields: list[dict], palette: Palette) -> str:
    from .palettes import rgb_to_hex

    if not palette:
        return "#ebdbb2"
    # Cycle through palette colors, skipping the first few because they tend to
    # be backgrounds / low-contrast darks.
    skip = 3
    usable = max(1, len(palette) - skip)
    index = (skip + (len(fields) % usable)) % len(palette)
    return rgb_to_hex(*palette[index])


def set_field(profile: dict, label: str, value: str, color: str | None = None) -> None:
    from .palettes import get_palette

    idx = find_field_index(profile, label)
    if idx >= 0:
        profile["fields"][idx]["value"] = value
        if color:
            profile["fields"][idx]["color"] = color
        return

    palette = get_palette(profile.get("palette", DEFAULT_PALETTE), config_dir())
    chosen_color = color or _next_color(profile.get("fields", []), palette)
    profile["fields"].append({"label": label, "value": value, "color": chosen_color})


def remove_field(profile: dict, label: str) -> bool:
    idx = find_field_index(profile, label)
    if idx >= 0:
        del profile["fields"][idx]
        return True
    return False


def set_image(profile: dict, source: Path | str) -> None:
    dest = avatar_path()
    shutil.copy2(source, dest)
    profile["image_path"] = str(dest)
