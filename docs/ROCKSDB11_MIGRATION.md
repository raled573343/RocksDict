# RocksDict → RocksDB 11.8.1: implementation contract

**Status:** Migration specification created; Rust code not yet ported. Do not release this branch.
**Base:** `main` at `337bb0d4610d33e4fbf2580d2ab03b251a709ea0`.
**Target:** native RocksDB `11.8.1`, `rust-rocksdb 0.53.0`, `rust-librocksdb-sys 0.48.1+11.8.1`, CPython `3.14t` (no GIL), Windows x64 and Linux manylinux_2_28 x64.
**Implementation branch:** `feat/rocksdb-11-8-1-cp314t`.

## Baseline and migration choice

RocksDict `Cargo.toml` currently uses a path Git submodule `rust-rocksdb` pinned to commit `4cf3c68a993b807bc54ff1c5293cdf49e62aaf72`. That Rust wrapper is `rocksdb 0.24.0`, and its native binding is `librocksdb-sys 0.17.1+9.8.4`.

Use the modern *pair* `rust-rocksdb 0.53.0` / `rust-librocksdb-sys 0.48.1+11.8.1` from https://github.com/zaidoon1/rust-rocksdb/releases/tag/v0.53.0. Its native Git submodule is https://github.com/facebook/rocksdb/tree/abeebd9630f11bd08c28b7bd43c7bdfc62050654 (RocksDB 11.8.1).

**Do not just move** the old `facebook/rocksdb` submodule pointer. The old `rocksdb` crate, C bindings, build script, and RocksDict direct FFI calls are all coupled to the 9.x generation. Using old and new `sys` crates together also risks Cargo `links = "rocksdb"` conflicts.

Suggested Cargo dependency aliases after compatibility work:

- `rocksdb`: `{ package = "rust-rocksdb", version = "=0.53.0", default-features = false, features = ["snappy", "lz4", "zstd", "zlib", "bzip2", "raw-ptr"] }`
- `librocksdb-sys`: `{ package = "rust-librocksdb-sys", version = "=0.48.1", default-features = false }`
- Carry existing feature forwarding `bindgen-runtime`, `bindgen-static`, `lto` and refresh `Cargo.lock` with Rust 1.91.1.
- If public safety/API differences require a pinned fork or a very small adapter crate, explicitly document and pin its commit. Do not link to two native RocksDB libraries.

Aliases retain the Rust import names `rocksdb` / `librocksdb_sys`, but **do not** magically retain methods. The newer `raw-ptr` feature exports `AsRawPtr`; its publicly supported handle coverage is limited. `src/rdict.rs`, `src/db_reference.rs`, `src/iter.rs`, `src/options.rs`, `src/snapshot.rs`, `src/sst_file_writer.rs`, `src/checkpoints.rs`, and `src/write_batch.rs` must be ported together.

## Implementation sequence (real code first)

1. **Make native backend buildable.** Replace the old Rust/native dependency pair and regenerate `Cargo.lock`; adapt Rust API calls and pointer/lifetime access with a compact compatibility module. Eliminate redundant `rust-rocksdb` Git submodule only after the dependency graph is clean. Confirm `cargo tree` has exactly one RocksDB backend, explicitly 11.8.1. Do not retain an unnoticed 9.x dependency.
2. **Keep Python compatibility.** All current exported `Rdict`, `Options`, column family, iterator, snapshot, checkpoint, batch, SST, ingest, compression paths must still work. Preserve `#[pymodule(gil_used = false)]`; explicitly revalidate `Send/Sync` and mutable pointer methods for 3.14t.
3. **Publish version provenance.** Provide a queryable `rocksdb_version()` equivalent exposed by the native library, or a compiled invariant backed by 11.8.1 native headers and release metadata. No wheel may be tagged 11.8.1 purely by filename. Keep the old `cp314t-v0.3.29` release untouched; use a separate version/release train, not the upstream-driven 9.x autobuilder.
4. **Expose new 11.x capabilities incrementally, not as imagined methods.** Start with valuable C-API-supported options and ingest/observability. For APIs only available in C++ (e.g., async callbacks) design a real new C/C++ bridge with explicit cancellation/lifetime/thread safety before exposing Python. Do not assume asyncio-native Windows support.
5. **One deliberate native CI run.** Branch pushes must not trigger native CI. After resolving compile issues, manually request **one** Windows/Linux x64 workflow dispatch, with Cargo/native cache and LLVM reuse. Do not trigger the old all-platform release matrix.
6. **Verify and release.** Offline wheel install; native version check; `sysconfig.Py_GIL_DISABLED=1`, `sys._is_gil_enabled() is False` *after import*; existing unit suite + focused backend tests; RocksDB 9.8.4 dataset read under 11.8.1 on a **disposable copy**; test write/reopen after upgrading the copy; no live 9.x DB modification; new separate Github Release only after two passing OS wheels.

## Acceptance gates

- [ ] Rust compilation succeeds with only one 11.8.1 backend on Windows/Linux.
- [ ] CPython 3.14t wheels: `cp314-cp314t-win_amd64` and `cp314-cp314t-manylinux_2_28_x86_64`.
- [ ] Native RocksDB 11.8.1 version is verified programmatically.
- [ ] Existing operations: default and raw mode, CRUD, multi-threaded writes/reads, column families, batch/SST ingest, snapshots, checkpoint, iterators, compression, DB close/reopen.
- [ ] Existing Python unit tests pass without skipped failing tests; no `|| true`.
- [ ] Old 9.x DB sample opens on 11.x **as copied test data**. Downgrade is not assumed.
- [ ] Concrete 11.x functionality is exposed and tested (scoped by available C API).
- [ ] Existing `main`, old Releases, and current scheduled upstream release workflow remain operational.
- [ ] Full report: modified files and commit, dependencies, native version, build flags, OS job URLs, checksums, concurrency/GIL tests, compatibility risk register, remaining unsupported 11.x APIs.

## Guardrails

- Prioritize working implementation, not endless audits, rebuild loops or AST churn.
- No expensive native Actions on every commit. Avoid unnecessary reconfigurations of cached LLVM/RocksDB compilation toolchain.
- No PyPI publishing unless separately requested.
- No destructive or write-mode migration on production DBs.
- RocksDB's supported upgrade direction does not guarantee that files written with new features remain readable by older RocksDB. Preserve backups and rollback by restoring files, not by opening them with 9.x.

## Ownership / next action

**Coding agent (Cursor or ChatGPT with authorized execution):** implement step 1 on this branch, explicitly report the first compile failures and fix them in source. Continue steps 2–6 without broad CI triggers.

**Review (ChatGPT):** inspect actual code diff and compilation output, reject stubs/no-op and unsupported compatibility claims, accept the native upgrade only when all gates pass.

**GitHub Issues note:** this repository currently has Issues disabled (GitHub API returned HTTP 410). This file serves as the durable task specification until Issues is enabled. Do not enable repository settings without explicit owner approval.
