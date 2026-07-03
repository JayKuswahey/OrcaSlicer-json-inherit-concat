#!/usr/bin/env python3
"""
Resolve and flatten the inheritance chain of OrcaSlicer JSON profile files.

Cross-platform replacement for orca-json-concat.sh.
Works on macOS, Linux, and Windows.
"""

from argparse import ArgumentParser
from datetime import datetime
from json import dump, load
from logging import DEBUG, INFO, basicConfig, getLogger
from pathlib import Path
from platform import system
from re import sub
from sys import exit as sys_exit
from tempfile import gettempdir

log = getLogger(__name__)


def echodate(message: str) -> None:
    """Log a message with a timestamp prefix, mirroring the bash echodate()."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log.info("%s %s", timestamp, message)


def echodate_debug(message: str) -> None:
    """Log a debug message with a timestamp prefix."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log.debug("%s %s", timestamp, message)


def get_inherits(filepath: Path) -> str | None:
    """
    Read the 'inherits' key from a JSON file.

    Returns the value as a string, or None if absent/null.
    """
    echodate_debug(f"Reading 'inherits' key from {filepath}")
    with open(filepath, encoding="utf-8") as fh:
        data = load(fh)
    value = data.get("inherits")
    if value is None:
        echodate_debug(f"No 'inherits' key found in {filepath}")
        return None
    echodate_debug(f"Found inherits='{value}' in {filepath}")
    return str(value)


def sanitize_filename(name: str) -> str:
    """Remove whitespace and punctuation from a filename (sans extension)."""
    return sub(r"[\s\W]+", "", name)


def default_profiles_location(component_name: str) -> Path:
    """
    Return the platform-specific default OrcaSlicer profiles directory.

    macOS:   ~/Library/Application Support/OrcaSlicer/system/BBL/<component>
    Linux:   ~/.config/OrcaSlicer/system/BBL/<component>
    Windows: %APPDATA%/OrcaSlicer/system/BBL/<component>
    """
    os_name = system()
    home = Path.home()

    if os_name == "Darwin":
        base = home / "Library" / "Application Support"
    elif os_name == "Windows":
        appdata = Path.home() / "AppData" / "Roaming"
        base = appdata
    else:
        # Linux and other Unix-like systems
        base = home / ".config"

    path = base / "OrcaSlicer" / "system" / "BBL" / component_name
    echodate_debug(f"Default profiles location for {os_name}: {path}")
    return path


def build_dependency_chain(
    file_to_check: Path,
    base_dir: Path,
    profiles_location: Path,
) -> list[Path]:
    """
    Walk the inheritance chain from the starting file up to the root ancestor.

    Returns the list in child-first order (will be reversed later for merging).
    """
    dependency_array: list[Path] = [file_to_check]

    ancestor_name = get_inherits(file_to_check)
    if ancestor_name is None:
        echodate("There is no dependency in this file, quitting.")
        sys_exit(12)

    echodate("We have a dependency, building tree.")

    while ancestor_name is not None:
        # Try current directory first
        check_file = base_dir / f"{ancestor_name}.json"
        echodate_debug(f"Checking {check_file}")

        if check_file.is_file():
            echodate_debug(f"File {check_file} found, adding to tree.")
            dependency_array.append(check_file)
            echodate_debug(f"File {check_file} added, checking more inheritance")
            ancestor_name = get_inherits(check_file)
        else:
            # Fall back to OrcaSlicer system profiles
            check_file = profiles_location / f"{ancestor_name}.json"
            echodate_debug(f"File not found, checking {check_file} now.")

            if not check_file.is_file():
                echodate_debug(f"File {check_file} not found either, quitting.")
                echodate(
                    f"Could not locate inherited file '{ancestor_name}.json' "
                    f"in '{base_dir}' or '{profiles_location}'."
                )
                sys_exit(20)

            echodate_debug(f"File {check_file} found, adding to tree.")
            dependency_array.append(check_file)
            echodate_debug(f"File {check_file} added, checking further inheritance")
            ancestor_name = get_inherits(check_file)

    echodate_debug("No further inheritance found.")
    return dependency_array


def merge_json_files(files: list[Path]) -> dict:
    """
    Merge multiple JSON files in order (earlier files are overridden by later ones).

    Removes the 'inherits' key, lowercases all top-level keys, and sorts them.
    """
    merged: dict = {}
    for filepath in files:
        echodate_debug(f"Merging {filepath}")
        with open(filepath, encoding="utf-8") as fh:
            data = load(fh)
        merged.update(data)

    # Remove the 'inherits' key
    merged.pop("inherits", None)

    # Lowercase all keys and sort alphabetically
    merged = dict(sorted(
        ((k.lower(), v) for k, v in merged.items()),
        key=lambda item: item[0],
    ))

    return merged


def parse_args() -> ArgumentParser:
    """Create and return the argument parser."""
    parser = ArgumentParser(
        description=(
            "Resolve and flatten the inheritance chain of "
            "OrcaSlicer JSON profile files."
        ),
    )
    parser.add_argument(
        "-f", "--file",
        required=True,
        help="Path to the starting JSON profile file.",
    )
    parser.add_argument(
        "-c", "--component",
        required=True,
        help="OrcaSlicer component type (e.g. process, filament, machine).",
    )
    parser.add_argument(
        "-l", "--profiles-location",
        default=None,
        help="Directory where OrcaSlicer system profiles live.",
    )
    parser.add_argument(
        "-t", "--target-location",
        default=None,
        help="Directory where the merged output file will be written.",
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser


def main() -> None:
    """Entry point for the OrcaSlicer JSON inheritance flattener."""
    parser = parse_args()
    args = parser.parse_args()

    # Configure logging based on debug flag
    level = DEBUG if args.debug else INFO
    basicConfig(level=level, format="%(message)s")

    file_to_check = Path(args.file)
    component_name: str = args.component

    # Validate required inputs
    if not file_to_check.is_file():
        echodate(f"File not found: {file_to_check}")
        sys_exit(10)

    # Derive sanitized filename for the output
    target_file_source = sanitize_filename(file_to_check.stem)

    # Determine profiles location
    if args.profiles_location:
        profiles_location = Path(args.profiles_location)
    else:
        profiles_location = default_profiles_location(component_name)

    # Determine target location (cross-platform temp directory)
    if args.target_location:
        target_location = Path(args.target_location)
    else:
        target_location = Path(gettempdir())

    echodate_debug("Setting up global variables")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_file = (
        target_location
        / f"orcaslicer_{component_name}_{target_file_source}_inherit_concat-{timestamp}.json"
    )

    echodate_debug("Setting up variable arrays")

    base_dir = Path(".")

    # Build the dependency chain (child → root)
    dependency_array = build_dependency_chain(
        file_to_check, base_dir, profiles_location,
    )

    echodate_debug("We now have the following array which needs to be reversed:")
    echodate_debug(" ".join(str(p) for p in dependency_array))

    # Reverse so merge order is root → child
    dependency_reversed = list(reversed(dependency_array))

    echodate_debug("Done! We now have the following reversed array:")
    echodate_debug(" ".join(str(p) for p in dependency_reversed))

    # Merge all JSON files
    echodate_debug("Let's build a full profile!")
    merged = merge_json_files(dependency_reversed)

    # Write result
    target_location.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as fh:
        dump(merged, fh, indent=2, ensure_ascii=False)

    echodate("Done! Cleaning up after myself!")
    echodate("Cleanup successful!")
    echodate(f"Please check your result in file {target_file}")


if __name__ == "__main__":
    main()
