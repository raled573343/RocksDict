# Engineering rules for GitHub Actions in this repository

These rules apply to every new or modified Actions workflow. Costly native
RocksDB compilation and downloads must never be designed first and cached later.

1. **Design caches before the first CI run.** Restore before installation or
   compilation, and save at the end using `if: always()` so successfully built
   intermediate dependencies are retained even when a later step fails.
2. For Rust/PyO3/native C++ builds, cover both Cargo `registry`/`git`
   downloads and the entire compatible `CARGO_TARGET_DIR`, including C++
   objects and compiled crates such as `once_cell`. Reuse pinned Rust toolchain
   installations when possible.
3. For Windows, cache pinned LLVM/Clang installations. For Linux manylinux
   containers, bind-mount host-persistent Cargo/Rust directories and cache
   downloaded `dnf` RPM packages; avoid moving `CARGO_HOME` away from the
   container's `rustup` binaries. Cache installed host toolchains separately.
4. Never share compiled `target` objects between OS/architecture/ABI,
   incompatible toolchains, source revisions or changed native build flags.
   Use an exact key for immutable outputs plus safe prefix restore keys for
   incremental builds. A cold cache should be populated on the first run.
5. Keep `Cargo.lock` committed, use `--locked`, and report cache-hit and
   runtime information in the Actions summary when relevant.
6. Do not cache credentials or sensitive data. Do not treat GitHub ephemeral
   runner images / Docker layer downloads as cached when they are not.
7. Avoid automatic expensive native builds on every source push. Prefer
   explicitly selected candidate stages and publish a release only after all
   required Windows/Linux wheel tests succeed.
8. A new workflow is **not ready** unless the above cache plan and
   failure-path save logic exist from its very first commit.

Applies to `.github/workflows/` and to future CI configuration additions.
