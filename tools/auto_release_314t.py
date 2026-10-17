"""Daily version discovery, upstream source preparation, and release verification.

All network calls use GitHub's authenticated API. New version sources are
taken from the upstream *release tag commit*, not the fork's current main.
Only GitHub Release assets are published; PyPI is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from zipfile import ZipFile

UPSTREAM = "rocksdict/RocksDict"
BASELINE = (0, 3, 29)
SEED_RUN = 39024425551  # Verified Windows+Linux 3.14t run, no rebuild needed
SEED_SHA = "1ae571fc5b107fc7f22b470fbded1e92ed3e4899"
VERSION_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")


def api(url: str, *, missing_ok: bool = False):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "rocksdict-cp314t-release-ci",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and missing_ok:
            return None
        raise


def version_tuple(tag: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def ref_to_commit(tag: str) -> str:
    data = api(f"https://api.github.com/repos/{UPSTREAM}/git/ref/tags/{tag}")
    obj = data["object"]
    for _ in range(4):
        if obj["type"] == "commit":
            sha = obj["sha"]
            assert SHA_RE.fullmatch(sha)
            return sha
        if obj["type"] != "tag":
            raise RuntimeError(f"Release tag {tag} does not resolve to a commit")
        obj = api(f"https://api.github.com/repos/{UPSTREAM}/git/tags/{obj['sha']}")["object"]
    raise RuntimeError(f"Tag has unexpectedly deep nesting: {tag}")


def write_outputs(**values: str) -> None:
    for key, value in values.items():
        print(f"{key}={value}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")


def release_exists(repo: str, tag: str) -> bool:
    release = api(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        missing_ok=True,
    )
    if not release:
        return False
    # Only a finished release with both desired wheel assets counts as complete.
    assets = [asset["name"] for asset in release.get("assets", [])]
    version = tag.removeprefix("cp314t-v")
    prefixes = f"rocksdict-{version}-cp314-cp314t-"
    return (
        not release["draft"]
        and "SHA256SUMS" in assets
        and sum(x.startswith(prefixes) and x.endswith("win_amd64.whl") for x in assets) == 1
        and sum(
            x.startswith(prefixes) and x.endswith("manylinux_2_28_x86_64.whl")
            for x in assets
        ) == 1
    )


def find_next_version() -> tuple[str, str] | None:
    repo = os.environ["GITHUB_REPOSITORY"]
    stable = {}
    for page in range(1, 7):
        records = api(
            f"https://api.github.com/repos/{UPSTREAM}/releases?per_page=100&page={page}"
        )
        for release in records:
            version = version_tuple(release["tag_name"])
            if (
                version is not None
                and version > BASELINE
                and not release["prerelease"]
                and not release["draft"]
            ):
                stable[version] = release["tag_name"]
        if len(records) < 100:
            break
    for version, tag in sorted(stable.items()):
        ver = tag.removeprefix("v")
        if not release_exists(repo, f"cp314t-v{ver}"):
            return ver, tag
    return None


def check() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    # Bootstrap the already-tested 0.3.29 once on any trigger (including cron).
    # Never invoke the build matrix merely because workflow code changed.
    if not release_exists(repo, "cp314t-v0.3.29"):
        run = api(f"https://api.github.com/repos/{repo}/actions/runs/{SEED_RUN}")
        if run["status"] != "completed" or run["conclusion"] != "success":
            raise RuntimeError("Pinned bootstrap run is not successful")
        if run["head_sha"] != SEED_SHA:
            raise RuntimeError("Pinned bootstrap run changed unexpectedly")
        write_outputs(
            mode="bootstrap", version="0.3.29", tag="v0.3.29",
            upstream_sha=ref_to_commit("v0.3.29"), run_id=str(SEED_RUN)
        )
        return

    found = find_next_version()
    if not found:
        write_outputs(mode="none", version="", tag="", upstream_sha="", run_id="")
        print("No new upstream stable version without a complete cp314t release.")
        return
    version, tag = found
    write_outputs(
        mode="build", version=version, tag=tag,
        upstream_sha=ref_to_commit(tag), run_id=""
    )


def replace_once(content: str, old: str, new: str, path: Path) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Unexpected upstream API change in {path}: {old!r} ({count} matches)")
    return content.replace(old, new)


def prepare(source: Path, version: str, commit_sha: str) -> None:
    if not SHA_RE.fullmatch(commit_sha):
        raise RuntimeError("Invalid pinned upstream source SHA")
    if subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip() != commit_sha:
        raise RuntimeError("Checkout does not match verified upstream release commit")
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    cargo = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((source / "Cargo.lock").read_text(encoding="utf-8"))
    if project["project"]["version"] != version or cargo["package"]["version"] != version:
        raise RuntimeError("Upstream source manifests do not match the release version")
    if not any(
        p["name"] == cargo["package"]["name"] and p["version"] == version
        for p in lock["package"]
    ):
        raise RuntimeError("Cargo.lock package version differs from upstream release")
    pyo3 = cargo["dependencies"]["pyo3"]
    pyver = pyo3["version"] if isinstance(pyo3, dict) else pyo3
    if tuple(int(x) for x in re.match(r"^(\d+)\.(\d+)", pyver).groups()) < (0, 27):
        raise RuntimeError(f"Unsupported PyO3 version: {pyver}")

    lib = source / "src/lib.rs"
    contents = lib.read_text(encoding="utf-8")
    if "#[pymodule(gil_used = false)]" not in contents:
        contents = replace_once(
            contents, "#[pymodule]\nfn rocksdict(",
            "#[pymodule(gil_used = false)]\nfn rocksdict(", lib
        )
        lib.write_text(contents, encoding="utf-8")

    # Serialize native object methods that operate on mutable C pointers;
    # reject upstream API churn rather than shipping an unchecked no-GIL wheel.
    for name, old, new in (
        ("src/checkpoints.rs", "pub fn create_checkpoint(&self, path: &str)",
         "pub fn create_checkpoint(&mut self, path: &str)"),
        ("src/sst_file_writer.rs", "fn open(&self, path: &str)",
         "fn open(&mut self, path: &str)"),
        ("src/sst_file_writer.rs", "fn file_size(&self) -> u64",
         "fn file_size(&mut self) -> u64"),
    ):
        target = source / name
        text = target.read_text(encoding="utf-8")
        if new not in text:
            text = replace_once(text, old, new, target)
            target.write_text(text, encoding="utf-8")

    tests = source / "test"
    if not tests.exists():
        raise RuntimeError("Upstream test suite not found; refusing untested release")
    print(f"Prepared upstream {version} from {commit_sha} with cp314t PyO3 changes")


def validate_dist(directory: Path, version: str) -> None:
    wheels = sorted(directory.glob("*.whl"))
    expected = {
        "win_amd64",
        "manylinux_2_28_x86_64",
    }
    if len(wheels) != 2:
        raise RuntimeError(f"Expected two wheels, found {wheels}")
    found = set()
    for wheel in wheels:
        parts = wheel.stem.split("-")
        if len(parts) != 5 or parts[:4] != ["rocksdict", version, "cp314", "cp314t"]:
            raise RuntimeError(f"Wrong wheel version/ABI: {wheel.name}")
        platform_tag = parts[4]
        if platform_tag not in expected or platform_tag in found:
            raise RuntimeError(f"Duplicate/invalid platform: {wheel.name}")
        found.add(platform_tag)
        with ZipFile(wheel) as archive:
            wheel_files = [p for p in archive.namelist() if p.endswith(".dist-info/WHEEL")]
            if len(wheel_files) != 1:
                raise RuntimeError(f"Invalid wheel metadata: {wheel.name}")
            metadata = archive.read(wheel_files[0]).decode()
            if f"Tag: cp314-cp314t-{platform_tag}" not in metadata:
                raise RuntimeError(f"Wheel tag mismatch: {wheel.name}")
    if found != expected:
        raise RuntimeError(f"Incomplete platforms: {found}")
    manifest = "".join(
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n"
        for wheel in wheels
    )
    (directory / "SHA256SUMS").write_text(manifest, encoding="utf-8")
    print(manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "prepare", "verify-dist"))
    parser.add_argument("--source", type=Path, default=Path("upstream"))
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--version", default="")
    parser.add_argument("--sha", default="")
    args = parser.parse_args()
    if args.command == "check":
        check()
    elif args.command == "prepare":
        prepare(args.source, args.version, args.sha)
    else:
        validate_dist(args.dist, args.version)


if __name__ == "__main__":
    main()
