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

    return parser


def cmd_show(args: argparse.Namespace) -> int:
    profile = load_profile()
    print(render(profile, width=args.term_width))
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
    }.get(command)
    if not func:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
