"""Stabilize pinned native submodule mtimes to prevent unnecessary C++ recompiles.

Only for the clean GitHub Actions checkout: git submodules contain immutable,
SHA-pinned source. The build cache key MUST include that exact submodule SHA.

Never run this on a developer worktree with uncommitted changes, where a
modified file must correctly invalidate Cargo's native build cache.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# All timestamps must be older than any cached build output.
SOURCE_DATE_EPOCH = 946684800  # 2000-01-01T00:00:00Z
SUBMODULE = Path("rust-rocksdb")


def run_git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        ["git", *(["-C", str(cwd)] if cwd else []), *args],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def main() -> None:
    if not SUBMODULE.is_dir():
        raise RuntimeError("Pinned rust-rocksdb submodule is absent")
    if not os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError("This timestamp normalization must only run in CI")

    # Require a clean working tree, including recursively initialized submodules.
    if run_git("status", "--porcelain", "--ignore-submodules=none"):
        raise RuntimeError("Dirty checkout: refusing timestamp normalization")

    revision = run_git("rev-parse", "HEAD", cwd=SUBMODULE)
    if len(revision) != 40:
        raise RuntimeError(f"Unexpected native source revision: {revision!r}")

    changed_files = 0
    changed_directories: list[Path] = []
    for base, dirnames, filenames in os.walk(SUBMODULE):
        dirnames[:] = [name for name in dirnames if name not in {".git", "target"}]
        directory = Path(base)
        changed_directories.append(directory)
        for name in filenames:
            if name == ".git":
                continue
            path = directory / name
            if not path.is_symlink() and path.is_file():
                os.utime(path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))
                changed_files += 1

    # Directory watches from build.rs also rely on mtime. Do this after files.
    for directory in reversed(changed_directories):
        if not directory.is_symlink():
            os.utime(directory, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))

    print(
        f"Normalized native source timestamps: revision={revision}, "
        f"files={changed_files}, dirs={len(changed_directories)}"
    )


if __name__ == "__main__":
    main()
