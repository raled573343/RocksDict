#!/usr/bin/env python3
"""Repack verified cp314t release wheels with initial RocksDB notices; never compile or publish."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import sys
import zipfile

EXPECTED = {
    "cp314t-v0.3.29": {
        "rocksdict-0.3.29-cp314-cp314t-win_amd64.whl": "84fbc81ea9387eb6106698f51b935aeb6214000c992782e36300a5c64b3fb4ae",
        "rocksdict-0.3.29-cp314-cp314t-manylinux_2_28_x86_64.whl": "f6617bd24556083f17504abe5b61469f83fda1a514bbba017e7e52c86d7c59dd",
    },
    "cp314t-v0.3.29-rocksdb11.8.1": {
        "rocksdict-0.3.29+rocksdb11.8.1-cp314-cp314t-win_amd64.whl": "ec0e1246c6a3394948fe1724e89ad133f550b506bacb7b4cd71d83ab9b5d05c9",
        "rocksdict-0.3.29+rocksdb11.8.1-cp314-cp314t-manylinux_2_28_x86_64.whl": "414c4a36d743b9f3a906a347de70731818f036a6dd094ed1325318e599c70a20",
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_line(path: str, data: bytes) -> list[str]:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return [path, "sha256=" + encoded, str(len(data))]


def repack(source: Path, output: Path, tag: str, licenses: Path) -> None:
    assert digest(source.read_bytes()) == EXPECTED[tag][source.name], f"original SHA mismatch: {source}"
    with zipfile.ZipFile(source) as wheel:
        assert wheel.testzip() is None, f"bad ZIP member in {source}"
        names = wheel.namelist()
        assert len(names) == len(set(names)), f"duplicate ZIP member in {source}"
        dist_infos = [n.removesuffix("METADATA") for n in names if n.endswith(".dist-info/METADATA")]
        assert len(dist_infos) == 1, f"wrong dist-info count in {source}"
        root = dist_infos[0]
        record = root + "RECORD"
        assert record in names
        entries = {n: wheel.read(n) for n in names if n != record}
        original_info = {info.filename: info for info in wheel.infolist()}
        assert root + "licenses/LICENSE" in entries, f"upstream MIT missing from {source}"
        additions = {
            "THIRD_PARTY/RocksDB-Apache-2.0.txt": (licenses / "Apache-2.0.txt").read_bytes(),
            "THIRD_PARTY/LevelDB.txt": (licenses / "LevelDB.txt").read_bytes(),
            "THIRD_PARTY/ATTRIBUTION.txt": (
                "Unofficial free-threaded CPython 3.14t RocksDict wheel, repacked without rebuilding native binaries.\n"
                f"Original GitHub tag: {tag}\n"
                f"Original wheel SHA-256: {EXPECTED[tag][source.name]}\n"
                "RocksDict Python wrapper: MIT; Copyright (c) 2021 Congyu (original LICENSE preserved).\n"
                "RocksDB native engine: Apache-2.0 option; inherited LevelDB notice included.\n"
                "IMPORTANT: compression/runtime license inventory is NOT COMPLETE. Not legally certified.\n"
                f"Original release: https://github.com/raled573343/RocksDict/releases/tag/{tag}\n"
            ).encode("utf-8"),
        }
        meta = entries[root + "METADATA"].decode("utf-8")
        header, separator, body = meta.partition("\n\n")
        assert separator and "Metadata-Version: 2.4" in header
        for relative_path, contents in additions.items():
            assert contents, relative_path
            path = root + "licenses/" + relative_path
            assert path not in entries, f"refusing to overwrite {path}"
            entries[path] = contents
            assert f"License-File: {relative_path}" not in header
            header += "\nLicense-File: " + relative_path
        entries[root + "METADATA"] = (header + separator + body).encode("utf-8")

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        for path in sorted(entries):
            writer.writerow(record_line(path, entries[path]))
        writer.writerow([record, "", ""])
        entries[record] = buffer.getvalue().encode("utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as patched:
            for name in names:
                if name != record:
                    patched.writestr(original_info[name], entries.pop(name))
            for name, contents in sorted(entries.items()):
                if name != record:
                    patched.writestr(name, contents, compress_type=zipfile.ZIP_DEFLATED)
            patched.writestr(record, entries[record], compress_type=zipfile.ZIP_DEFLATED)

    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as patched:
        assert patched.testzip() is None
        for name in original.namelist():
            if name.endswith((".so", ".pyd", ".dll")):
                assert original.read(name) == patched.read(name), f"native binary changed: {name}"
        contents = {name: patched.read(name) for name in patched.namelist()}
        rows = list(csv.reader(io.StringIO(contents[record].decode("utf-8"))))
        assert len(rows) == len(contents)
        assert {row[0] for row in rows} == set(contents)
        for path, recorded_hash, size in rows:
            if path == record:
                assert recorded_hash == size == ""
            else:
                assert [path, recorded_hash, size] == record_line(path, contents[path]), path
    print(f"{tag}/{output.name}: {digest(output.read_bytes())}")


def main() -> None:
    sources, target, licenses = map(Path, sys.argv[1:])
    assert all((licenses / name).is_file() for name in ("Apache-2.0.txt", "LevelDB.txt"))
    for tag, expected_files in EXPECTED.items():
        directory = sources / tag
        found = {path.name for path in directory.glob("*.whl")}
        assert found == set(expected_files), f"unexpected wheel files for {tag}: {found}"
        sums = []
        for filename in sorted(expected_files):
            output = target / tag / filename
            repack(directory / filename, output, tag, licenses)
            sums.append(f"{digest(output.read_bytes())}  {filename}\n")
        (target / tag / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")


if __name__ == "__main__":
    main()
