# Native-library notice sources for cp314t post-build repackaging

These texts are copied from upstream projects, intended to accompany native compression capabilities potentially incorporated into the pinned RocksDB builds. They are added to a **wheel packaging preview** without modifying compiled native extensions. Each wheel additionally preserves its original RocksDict MIT notice, RocksDB's Apache-2.0 text and inherited LevelDB notices.

| File | Project / version used for notice | Source |
| --- | --- | --- |
| `Snappy-BSD.txt` | Snappy 1.2.1 | https://github.com/google/snappy/blob/1.2.1/COPYING |
| `LZ4-BSD.txt` | LZ4 1.10.0 | https://github.com/lz4/lz4/blob/v1.10.0/lib/LICENSE |
| `Zstd-BSD.txt` | Zstandard 1.5.7 | https://github.com/facebook/zstd/blob/v1.5.7/LICENSE |
| `Zlib.txt` | zlib license text from upstream 1.3.1 | https://github.com/madler/zlib/blob/v1.3.1/LICENSE |
| `Bzip2.txt` | bzip2/libbzip2 1.0.8 (Julian Seward) | https://gitlab.com/bzip2/bzip2/-/blob/bzip2-1.0.8/LICENSE ; mirrored text: https://github.com/commontk/bzip2/blob/master/LICENSE |

`Cargo.lock` and the CycloneDX SBOM **embedded in each original wheel** identify native-related crates including `bzip2-sys`, `libz-sys`, `lz4-sys` and `zstd-sys`. The Rust RocksDB build features also request Snappy. The SBOM includes **53–66 Cargo components** depending on variant/platform, some of which are build-time dependencies and not all of which are proven to be present in the compiled binary.

**Not a finished legal bill of materials:** exact static linking and required copyright/license notices for Rust crates and any vendored code remain to be audited. The `zlib` notice is a canonical upstream text; its exact packaged source revision has not yet been independently tied to the release binary. Including extra allowed notices is not equivalent to verifying every obligation. Independent legal review is recommended for a formal compliance claim.

See [the independent four-wheel preview verification](https://github.com/raled573343/rocksdict-rocksdb11/blob/main/WHEEL_PREVIEW_VERIFICATION_2026-10-17.md).