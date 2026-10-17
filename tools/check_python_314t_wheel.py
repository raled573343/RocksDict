"""Проверка именно cp314t wheel и реальной работы расширения без GIL.

Это smoke/integration test, а не формальное доказательство потокобезопасности API.
"""

from __future__ import annotations

import argparse
import platform
import sys
import sysconfig
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile


def require_no_gil(stage: str) -> None:
    assert sys.version_info[:2] == (3, 14), sys.version
    assert sysconfig.get_config_var("Py_GIL_DISABLED") == 1, (
        "Interpreter is not CPython 3.14t"
    )
    assert not sys._is_gil_enabled(), f"GIL was enabled at stage: {stage}"
    assert sys.maxsize > 2**32, "x64 Python is required"
    assert platform.machine().lower() in ("amd64", "x86_64"), platform.machine()


def check_wheel(platform_tag: str) -> Path:
    wheels = sorted(Path("dist").glob("*.whl"))
    assert len(wheels) == 1, f"Expected exactly one wheel, got: {wheels}"
    wheel = wheels[0]
    parts = wheel.stem.split("-")
    assert len(parts) == 5, f"Unexpected wheel filename: {wheel}"
    dist, version, py_tag, abi_tag, found_platform = parts
    assert dist.lower() == "rocksdict", wheel
    assert version, wheel
    assert py_tag == "cp314" and abi_tag == "cp314t", (
        f"Expected cp314-cp314t, got {wheel.name}"
    )
    assert found_platform == platform_tag, (
        f"Expected {platform_tag}, got {found_platform}"
    )
    with ZipFile(wheel) as archive:
        wheel_files = [p for p in archive.namelist() if p.endswith(".dist-info/WHEEL")]
        assert len(wheel_files) == 1
        metadata = archive.read(wheel_files[0]).decode("utf-8")
        assert f"Tag: cp314-cp314t-{platform_tag}" in metadata, metadata
    print(f"Verified native cp314t wheel: {wheel.name}")
    return wheel


def smoke_test() -> None:
    require_no_gil("before importing rocksdict")

    from rocksdict import Options, Rdict

    # If the PyO3 module has not opted in to free-threading, import may re-enable GIL.
    require_no_gil("after importing rocksdict")

    count = 120
    workers = 8
    with tempfile.TemporaryDirectory(prefix="rocksdict-314t-") as base:
        path = str(Path(base) / "db")
        db = Rdict(path, options=Options(raw_mode=True))

        def thread_job(worker: int) -> None:
            for j in range(count):
                key = f"worker-{worker}-key-{j}".encode()
                value = f"value-{worker}-{j}".encode()
                db[key] = value
                assert db[key] == value, (worker, j)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(thread_job, range(workers)))
        assert len(db) == workers * count
        db.close()

        # Check that database data survives close/open.
        db = Rdict(path, options=Options(raw_mode=True))
        for worker in range(workers):
            for j in range(count):
                key = f"worker-{worker}-key-{j}".encode()
                assert db[key] == f"value-{worker}-{j}".encode()
        db.close()
        Rdict.destroy(path)

    require_no_gil("after concurrent read/write smoke test")
    print(f"PASS: {workers} threads, {workers * count} records, persistent reopen, GIL off")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("win_amd64", "manylinux_2_28_x86_64"), required=True)
    parser.add_argument("--wheel-only", action="store_true")
    args = parser.parse_args()
    require_no_gil("start")
    check_wheel(args.platform)
    if not args.wheel_only:
        smoke_test()


if __name__ == "__main__":
    main()
