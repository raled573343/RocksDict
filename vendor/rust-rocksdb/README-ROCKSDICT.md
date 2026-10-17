# rust-rocksdb wrapper 0.53.0 (RocksDB 11.8.1)

Pinned original source: https://github.com/zaidoon1/rust-rocksdb/tree/c8b2e2c3a6939ea2cd35ff073c10b1e431615d88

This local copy contains the Rust wrapper source, not the native RocksDB C++
sources. Native C++ comes exclusively from `rust-librocksdb-sys =0.48.1`
(the vendored library in that crate is RocksDB 11.8.1).

Minimal intentional deviations from upstream:

1. Remove the upstream Cargo workspace member/path dependency on
   `librocksdb-sys`. Use one exact published native dependency.
2. Exclude the upstream `[[bench]] hot_paths` target (bench files are not vendored).
3. Add `ColumnFamilyDescriptor::into_name_and_options` so RocksDict can
   preserve the real native per-column-family Options loaded from disk,
   rather than using defaults or accessing private layout through unsafe.

Keep `LICENSE` (Apache-2.0). Any later upstream sync must compare against
the above commit and re-evaluate both modifications. All RocksDB 11.8.1
native ABI checks are enforced by `build.rs` and
`src/rocksdb11_bridge.cc` in the main application crate.

The old 9.8.4 Git submodule is removed only on the migration branch.
