"""Interactive profile setup wizard."""

from __future__ import annotations

from pathlib import Path

from .palettes import list_palettes
from .profile import (
    DEFAULT_LOGO_WIDTH,
    config_dir,
    detect_os,
    save_profile,
    set_field,
    set_image,
)


def _ask(prompt: str, default: str | None = None) -> str:
    if default is not None:
        full = f"{prompt} [{default}]: "
    else:
        full = f"{prompt}: "
    value = input(full).strip()
    if not value and default is not None:
        return default
    return value


def _ask_bool(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    value = input(prompt + suffix).strip().lower()
    if not value:
        return default
    return value in ("y", "yes", "true", "1", "on")


def run() -> None:
    print("Welcome to personfetch! Let's build your card.\n")

    profile = {
        "version": 1,
        "image_path": None,
        "palette": "gruvbox",
        "logo_width": DEFAULT_LOGO_WIDTH,
        "gutter": 3,
        "dither": True,
        "separator": ":",
        "fields": [],
    }

    name = _ask("Name")
    if name:
        set_field(profile, "name", name)

    age = _ask("Age (optional)")
    if age:
        set_field(profile, "age", age)

    location = _ask("Location (optional)")
    if location:
        set_field(profile, "location", location)

    os_val = _ask("OS", default=detect_os())
    set_field(profile, "os", os_val)

    interests = _ask("Interests")
    if interests:
        set_field(profile, "interests", interests)

    while True:
        extra = _ask(
            "Add another field? (label, or leave blank to finish)", default=""
        )
        if not extra:
            break
        val = _ask(f"Value for {extra}")
        if val:
            set_field(profile, extra, val)

    palettes = list_palettes(config_dir())
    print(f"\nAvailable palettes: {', '.join(palettes)}")
    palette = _ask("Palette", default="gruvbox")
    if palette:
        profile["palette"] = palette

    profile["dither"] = _ask_bool("Dither image", default=True)

    width = _ask("Logo width in terminal cells", default=str(DEFAULT_LOGO_WIDTH))
    try:
        profile["logo_width"] = max(10, min(120, int(width)))
    except ValueError:
        profile["logo_width"] = DEFAULT_LOGO_WIDTH

    img = _ask("Path to a photo (optional)")
    if img:
        p = Path(img).expanduser()
        if p.exists():
            set_image(profile, p)
        else:
            print(f"Warning: image not found at {p}")

    save_profile(profile)
    print("\nProfile saved! Run `personfetch` to see your card.")
