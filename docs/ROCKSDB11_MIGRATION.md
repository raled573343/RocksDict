## Implementation checkpoint — source prepared, compilation intentionally paused

The migration branch contains an actual RocksDB 11.8.1 port, not merely an
architecture document. Its implementation now includes:

- One vendored Rust wrapper based on `zaidoon1/rust-rocksdb@c8b2e2c3a6939ea2cd35ff073c10b1e431615d88`
  (version 0.53.0). All 51 upstream Rust source/manifest/license files are
  present; only its Cargo manifest and `ColumnFamilyDescriptor` accessor differ.
- One native engine dependency `rust-librocksdb-sys =0.48.1`, whose vendored
  Facebook RocksDB version is 11.8.1. The old `rust-rocksdb` Git submodule
  and its `.gitmodules` entry have been removed **from this branch only**.
- `src/compat.rs`: lifetime-aware column-family handles and public raw-pointer
  access, without assuming the private layout of rust-rocksdb Rust types.
- `src/rocksdb11_bridge.cc` + `src/wide_columns.rs`: owned C ABI wrappers for
  RocksDB 11 GetEntity, PutEntity and iterator columns; exact native version
  compile-time check `ROCKSDB_MAJOR/MINOR/PATCH == 11/8/1`.
- `src/snapshot.rs`, `src/iter.rs`, `src/options.rs`: snapshot read path,
  lifetime-safe iterator bounds and new RocksDB 11.8 options.
- Python `native_rocksdb_version()`, typing stubs, and
  `test/test_rocksdb11.py` for native ABI, snapshots, wide columns and no-GIL.
- Candidate package version `0.3.29+rocksdb11.8.1`, separate from published
  `0.3.29` wheels.

### Completed non-build checks

- All 51 expected vendor files exist; only the two documented intentional
  source changes differ from upstream.
- Cargo manifests point to the **same** 11.8.1 native dependency. The application
  enables `multi-threaded-cf`, `raw-ptr` and PyO3 0.27 no-GIL opt-in.
- Unused 9.8.4 Rust submodule was removed from the migration branch.
- GitHub Actions in this branch is **workflow_dispatch only**, so source edits
  cannot trigger full native rebuilds. `main` and the established 9.x wheel
  releases are unchanged.

### Pending, and not falsely marked as passed

- **Cargo.lock:** the checked-in lockfile still reflects the old 9.x backend.
  The next controlled `check-linux` run must regenerate the lock for the
  local vendored package and commit the resulting lockfile.
- **Compilation:** Rust/C++ source compatibility is not yet compiler-verified.
  The pre-port diagnostic run failed in the native build script because the
  workflow supplied an empty `LIBCLANG_PATH`. The workflow now searches for
  the installed libclang library and fails immediately if absent.
- The new C++ bridge follows the private C API wrapper representation from
  RocksDB 11.8.1 `db/c.cc`. That is intentionally version-pinned and **must**
  receive extra build/runtime review and C++ exception/memory-safety testing
  before release. Native source changes or system-linked RocksDB are not
  supported without revisiting it.
- **No new candidate wheels** have been built; no integration test has passed.
  In particular, the Python 3.14t no-GIL and 9.x DB-copy upgrade gates remain
  open. Do not publish or merge to `main` before those pass.

### Next controlled build action (only when approved)

Use **Actions → RocksDB 11 migration - manual candidate build** on
`feat/rocksdb-11-8-1-cp314t`, stage `check-linux`. This resolves
`Cargo.lock` and yields precise Rust errors, compiling only Linux.
Port any remaining APIs based on *those errors*. Only after the full
Linux compile passes, explicitly dispatch `wheels-both` for Windows and
manylinux tests. Never bypass acceptance gates with `|| true`.

---

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


## Implementation checkpoint — 2026-10-17 (source-only phase)

**Current state:** source port is being populated and reviewed in small
commits. **No new native build has been started since the manual-only trigger
was installed.** Do not merge or publish yet.

Implemented in this branch:
- Vendored complete Rust wrapper `rust-rocksdb 0.53.0`, paired with one native
  sys crate `rust-librocksdb-sys 0.48.1+11.8.1`; removed old native gitlink.
- Retained exact OPTIONS-file column-family configuration using a minimal
  consuming wrapper accessor.
- Added lifetime-safe owning column-family handles with native refcounts.
- Added a narrow C++11.8 bridge for `GetEntity`, `PutEntity`,
  `Iterator::columns`, compile-time native-version assertion and Python
  `native_rocksdb_version()`.
- Made iterator key/value buffers copied while mutex is held, including empty
  binary keys. Held snapshot ownership for iterators after the Snapshot object
  is destroyed. Kept prefix bound buffers alive.
- Updated open-with-TTL signature to `Duration` with negative-input rejection.
- Exposed native 11.x read-executor, background OPTIONS cleanup,
  flush-listener wait, selected external SST ingest controls, and
  `Rdict.verify_file_checksums()`.
- Added Python stubs and regression tests for those behaviors.

**Before any build attempts:** reconcile the migration `Cargo.lock`. The
GitHub candidate workflow currently generates a fresh lockfile before
compilation; the committed lockfile is still the old RocksDB-9 generation and
must not be treated as a reproducible RocksDB-11 lock. Once resolved, run only
the manually selected `check-linux` stage first to obtain concrete compiler
errors; fix those in source before `wheels-both`. The previous diagnostic run
#39027278753 failed before Rust type checking due to a missing
`LIBCLANG_PATH`; its workflow setup was fixed. This does **not** establish
successful Rust/C++ compilation of the new code.

**Release safety:** existing `main`, daily upstream-version builder and
`cp314t-v0.3.29` remain separate and unchanged by this branch. No destructive
production database migration.
