"""Bump the Atlas version in one place and keep the package in sync.

    python scripts/bump_version.py patch          # 1.0.0 -> 1.0.1
    python scripts/bump_version.py minor          # 1.0.0 -> 1.1.0
    python scripts/bump_version.py major          # 1.0.0 -> 2.0.0
    python scripts/bump_version.py --set 1.2.0
    python scripts/bump_version.py patch --dry-run

Only ``pyproject.toml`` and ``atlas/__init__.py`` are edited. The release
workflow checks that the tag matches ``pyproject.toml`` before building.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise SystemExit("Could not find a project version in pyproject.toml")
    version = match.group(1)
    if not SEMVER.match(version):
        raise SystemExit(f"pyproject version {version!r} is not plain semantic versioning")
    return version


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(part_) for part_ in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def apply(root: Path, version: str, dry_run: bool) -> None:
    pyproject = root / "pyproject.toml"
    init = root / "atlas" / "__init__.py"
    if not init.exists():
        raise SystemExit(f"Missing {init}")

    py_text = pyproject.read_text(encoding="utf-8")
    new_py = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        py_text,
        count=1,
        flags=re.MULTILINE,
    )

    init_text = init.read_text(encoding="utf-8")
    new_init, count = re.subn(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{version}"',
        init_text,
        count=1,
    )
    if count != 1:
        raise SystemExit("Could not find __version__ in atlas/__init__.py")

    if dry_run:
        print(f"[dry-run] would set version {version}")
        return
    pyproject.write_text(new_py, encoding="utf-8")
    init.write_text(new_init, encoding="utf-8")
    print(f"Bumped Atlas to {version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", nargs="?", choices=["patch", "minor", "major"])
    parser.add_argument("--set", dest="explicit", help="Set an exact semantic version.")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.part and not args.explicit:
        parser.error("choose patch, minor, major, or --set X.Y.Z")
    if args.explicit and not SEMVER.match(args.explicit):
        parser.error("--set must look like 1.2.3")

    current = read_version(args.root)
    target = args.explicit or bump(current, args.part or "patch")
    if target == current:
        raise SystemExit(f"Version is already {current}")
    apply(args.root, target, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
