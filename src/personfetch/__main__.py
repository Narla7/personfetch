"""CLI entry point for personfetch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .palettes import list_palettes
from .profile import (
    config_dir,
    load_profile,
    profile_path,
    remove_field,
    save_profile,
    set_field,
    set_image,
)
from .render import render
from .wizard import run as run_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="personfetch",
        description="fastfetch, but for people.",
    )
    parser.add_argument(
        "--width",
        type=int,
        dest="term_width",
        help="Force terminal width for layout",
    )
    img_mode = parser.add_mutually_exclusive_group()
    img_mode.add_argument(
        "--image", action="store_true", help="Render the card as an inline image (kitty graphics)"
    )
    img_mode.add_argument(
        "--kitty", action="store_true", help="Alias for --image"
    )
    img_mode.add_argument(
        "--ascii", action="store_true", help="Force ASCII half-block rendering (default)"
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init", help="Run the interactive setup wizard")
    sub.add_parser("show", help="Show your card (default)")
    sub.add_parser("list", help="List profile fields")

    setp = sub.add_parser("set", help="Set or add a field")
    setp.add_argument("label")
    setp.add_argument("value")
    setp.add_argument("--color", help="Hex color for the label", default=None)

    addp = sub.add_parser("add", help="Add a new field (alias for set)")
    addp.add_argument("label")
    addp.add_argument("value")
    addp.add_argument("--color", help="Hex color for the label", default=None)

    rmp = sub.add_parser("rm", help="Remove a field")
    rmp.add_argument("label")

    imgp = sub.add_parser("image", help="Set your portrait image")
    imgp.add_argument("path", help="Path to image file")
    imgp.add_argument("--palette", help="Palette name")
    imgp.add_argument("--width", type=int, help="Logo width")
    imgp.add_argument("--no-dither", action="store_true", help="Disable dithering")

    sub.add_parser("config", help="Print the config file path")
    sub.add_parser("palettes", help="List available palettes")
    sub.add_parser("doctor", help="Diagnose terminal image support")

    expp = sub.add_parser("export", help="Render your card to a shareable PNG")
    expp.add_argument("-o", "--output", default="personfetch.png", help="Output PNG path")
    expp.add_argument("--font-size", type=int, default=30, help="Font size in pixels")

    return parser


def _mode_from_args(args: argparse.Namespace) -> str:
    import os as _os

    if getattr(args, "kitty", False) or getattr(args, "image", False):
        return "image"
    if getattr(args, "ascii", False):
        return "ascii"
    if _os.environ.get("PERSONFETCH_KITTY", "").lower() in ("1", "true", "yes", "kitty"):
        return "image"
    return "ascii"


def cmd_show(args: argparse.Namespace) -> int:
    profile = load_profile()
    print(render(profile, width=args.term_width, mode=_mode_from_args(args)))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    run_wizard()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    profile = load_profile()
    for field in profile.get("fields", []):
        print(f"{field['label']}: {field['value']}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    profile = load_profile()
    set_field(profile, args.label, args.value, color=args.color)
    save_profile(profile)
    print(f"Set {args.label} = {args.value}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    return cmd_set(args)


def cmd_rm(args: argparse.Namespace) -> int:
    profile = load_profile()
    if remove_field(profile, args.label):
        save_profile(profile)
        print(f"Removed {args.label}")
    else:
        print(f"No field named {args.label}")
        return 1
    return 0


def cmd_image(args: argparse.Namespace) -> int:
    profile = load_profile()
    src = Path(args.path).expanduser()
    if not src.exists():
        print(f"Error: file not found {src}", file=sys.stderr)
        return 1
    set_image(profile, src)
    if args.palette:
        profile["palette"] = args.palette
    if args.width:
        profile["logo_width"] = max(10, min(120, args.width))
    profile["dither"] = not args.no_dither
    save_profile(profile)
    print(f"Portrait set to {src}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    print(profile_path())
    return 0


def cmd_palettes(args: argparse.Namespace) -> int:
    print("Available palettes:")
    for name in list_palettes(config_dir()):
        print(f"  - {name}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from .export import export_png

    profile = load_profile()
    dest = export_png(profile, args.output, font_size=args.font_size)
    print(f"Card exported to {dest}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import os
    from pathlib import Path as _Path

    from . import kitty as kitty_mod

    profile = load_profile()
    image_path = profile.get("image_path")
    print(f"stdout is a tty: {sys.stdout.isatty()}")
    print(f"TERM={os.environ.get('TERM', '')!r} "
          f"TMUX={'set' if os.environ.get('TMUX') else 'unset'} "
          f"KITTY_WINDOW_ID={os.environ.get('KITTY_WINDOW_ID', '')!r}")
    print(f"image: {image_path or '(none)'}"
          + ("" if image_path and _Path(image_path).exists() else " (missing)" if image_path else ""))
    if image_path and _Path(image_path).exists():
        try:
            from PIL import Image as _Image

            with _Image.open(image_path) as _im:
                print(f"avatar: {_im.size[0]}x{_im.size[1]} {_im.format} "
                      f"{_Path(image_path).stat().st_size} bytes")
        except Exception as exc:
            print(f"avatar: unreadable ({exc})")
    print(f"kitty probe: {'SUPPORTED' if kitty_mod.kitty_supported() else 'not supported -> ascii fallback'}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "show"
    func = {
        "show": cmd_show,
        "init": cmd_init,
        "list": cmd_list,
        "set": cmd_set,
        "add": cmd_add,
        "rm": cmd_rm,
        "image": cmd_image,
        "config": cmd_config,
        "palettes": cmd_palettes,
        "export": cmd_export,
        "doctor": cmd_doctor,
    }.get(command)
    if not func:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
