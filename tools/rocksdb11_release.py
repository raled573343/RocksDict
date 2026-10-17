"""Fail-closed packaging gate for RocksDict with native RocksDB 11.8.1.

This script only validates already TESTED wheel binaries produced by the
two-platform cp314t Actions matrix. It neither builds nor uploads packages.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

REQUIRED = {"win_amd64", "manylinux_2_28_x86_64"}


def validate(dist: Path, *, manifest: Path = Path("pyproject.toml")) -> list[Path]:
    project = tomllib.loads(manifest.read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if "+rocksdb11.8.1" not in version:
        raise ValueError(f"Refusing a non-RocksDB-11 candidate: {version}")
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 2:
        raise ValueError(f"Expected exactly 2 tested platform wheels, found {len(wheels)}")
    seen: set[str] = set()
    for wheel in wheels:
        parts = wheel.stem.split("-")
        if len(parts) != 5:
            raise ValueError(f"Unexpected wheel filename: {wheel.name}")
        name, found_version, interpreter, abi, platform = parts
        if name != "rocksdict" or found_version != version:
            raise ValueError(f"Wheel version mismatch: {wheel.name} versus {version}")
        if (interpreter, abi) != ("cp314", "cp314t"):
            raise ValueError(f"Not a free-threaded CPython 3.14 wheel: {wheel.name}")
        if platform not in REQUIRED or platform in seen:
            raise ValueError(f"Duplicate/unexpected platform: {wheel.name}")
        seen.add(platform)

        with ZipFile(wheel) as archive:
            matching = [name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")]
            metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(matching) != 1 or len(metadata) != 1:
                raise ValueError(f"Invalid wheel metadata layout: {wheel.name}")
            tags = archive.read(matching[0]).decode("utf-8")
            if f"Tag: cp314-cp314t-{platform}" not in tags:
                raise ValueError(f"Wheel tag does not match filename: {wheel.name}")
            package = archive.read(metadata[0]).decode("utf-8")
            if f"Version: {version}" not in package:
                raise ValueError(f"Embedded package version differs: {wheel.name}")

    if seen != REQUIRED:
        raise ValueError(f"Missing platform wheel: {REQUIRED - seen}")
    sha = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in wheels
    )
    (dist / "SHA256SUMS").write_text(sha, encoding="utf-8")
    print(f"PASS: 2 CPython 3.14t wheel files for RocksDB 11.8.1 candidate {version}")
    print(sha)
    return wheels


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    try:
        validate(args.dist, manifest=args.project)
    except (ValueError, OSError, KeyError) as exc:
        print(f"RELEASE BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
