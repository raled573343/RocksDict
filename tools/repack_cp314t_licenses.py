#!/usr/bin/env python3
"""Repack pinned cp314t release wheels with native notices and accurate release metadata; no compilation."""
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
            "THIRD_PARTY/Snappy.txt": (licenses / "third-party" / "Snappy-BSD.txt").read_bytes(),
            "THIRD_PARTY/LZ4.txt": (licenses / "third-party" / "LZ4-BSD.txt").read_bytes(),
            "THIRD_PARTY/Zstd.txt": (licenses / "third-party" / "Zstd-BSD.txt").read_bytes(),
            "THIRD_PARTY/Zlib.txt": (licenses / "third-party" / "Zlib.txt").read_bytes(),
            "THIRD_PARTY/Bzip2.txt": (licenses / "third-party" / "Bzip2.txt").read_bytes(),
            "THIRD_PARTY/ATTRIBUTION.txt": (
                "Unofficial free-threaded CPython 3.14t RocksDict wheel, repacked without rebuilding native binaries.\n"
                f"Original GitHub tag: {tag}\n"
                f"Original wheel SHA-256: {EXPECTED[tag][source.name]}\n"
                "RocksDict Python wrapper: MIT; Copyright (c) 2021 Congyu (original LICENSE preserved).\n"
                "RocksDB native engine: Apache-2.0 option; inherited LevelDB notice included.\n"
                "Compression notices: Snappy, LZ4, Zstandard, zlib, bzip2.\n"
                "SBOM lists Rust crates and their declared licenses; some are build-only and others linked.\n"
                "IMPORTANT: full Rust crate/binary attribution audit is NOT COMPLETE. Not legally certified.\n"
                f"Original release: https://github.com/raled573343/RocksDict/releases/tag/{tag}\n"
            ).encode("utf-8"),
        }
        meta = entries[root + "METADATA"].decode("utf-8")
        header, separator, body = meta.partition("\n\n")
        assert separator and "Metadata-Version: 2.4" in header
        # Restrict claims to these independently built free-threaded wheels, not upstream PyPI.
        is_rocksdb11 = tag.endswith("rocksdb11.8.1")
        source_revision = (
            "b2958391ddea0530e0f299295f7b5fad43590a3a"
            if is_rocksdb11 else "1ae571fc5b107fc7f22b470fbded1e92ed3e4899"
        )
        header_lines = header.split("\n")
        header_lines = [line for line in header_lines if not (
            line.startswith("Classifier: ") or line.startswith("Summary: ")
        )]
        header_lines += [
            "Classifier: Development Status :: 3 - Alpha",
            "Classifier: Programming Language :: Python :: 3.14",
            "Classifier: Programming Language :: Python :: Implementation :: CPython",
            "Classifier: Operating System :: Microsoft :: Windows",
            "Classifier: Operating System :: POSIX :: Linux",
            "Classifier: Topic :: Database",
            "Summary: Unofficial RocksDict free-threaded CPython 3.14t x64 wheel"
                     + (" with RocksDB 11.8.1" if is_rocksdb11 else ""),
        ]
        header = "\n".join(header_lines)
        body = (
            "# Unofficial RocksDict wheel for free-threaded Python 3.14t\n\n"
            + ("Native RocksDB: **11.8.1** (experimental upgrade).\n\n"
               if is_rocksdb11 else
               "Upstream-aligned RocksDict 0.3.29 native engine (no RocksDB 11 upgrade).\n\n")
            + "This wheel is built specifically for free-threaded CPython 3.14t on "
              "Windows x64 or Linux x86-64 (glibc 2.28+). It is not compatible "
              "with regular CPython 3.14, macOS, or ARM64.\n\n"
            + "Independent community build — not affiliated with or endorsed by "
              "the RocksDict upstream developers or Meta/RocksDB.\n\n"
            + "**Install the wheel downloaded from the corresponding GitHub Release** "
              "with your Python 3.14t interpreter; the PyPI command "
              "`pip install rocksdict` does not select these exact builds.\n\n"
            + "Original RocksDict: https://github.com/rocksdict/RocksDict\n\n"
            + f"Verified source commit: https://github.com/raled573343/RocksDict/commit/{source_revision}\n\n"
            + f"Original binary release: https://github.com/raled573343/RocksDict/releases/tag/{tag}\n\n"
            + "Independent distribution documentation, release links, licensing and audit status: "
              "https://github.com/raled573343/rocksdict-rocksdb11\n\n"
            + "This post-processed wheel retains the same native extension bytes as the original. "
              "Added license notices do not constitute a full legal audit or safety certification. "
              "Test concurrent database workloads and back up data before trying newer RocksDB.\n"
        )
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
        metadata = contents[root + "METADATA"].decode("utf-8")
        assert "Classifier: Development Status :: 5 - Production/Stable" not in metadata
        assert "Classifier: Development Status :: 3 - Alpha" in metadata
        assert "Summary: Unofficial RocksDict free-threaded CPython 3.14t x64 wheel" in metadata
        assert "RocksDict / SpeeDict" not in metadata, "old upstream README still embedded"
        for rel_path in additions:
            assert f"License-File: {rel_path}" in metadata
            assert root + "licenses/" + rel_path in contents
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
    required = ("Apache-2.0.txt", "LevelDB.txt",
                "third-party/Snappy-BSD.txt", "third-party/LZ4-BSD.txt",
                "third-party/Zstd-BSD.txt", "third-party/Zlib.txt",
                "third-party/Bzip2.txt")
    assert all((licenses / name).is_file() for name in required), "missing native license text"
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
