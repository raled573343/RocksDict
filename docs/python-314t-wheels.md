# CPython 3.14t (no-GIL) wheels

The dedicated [GitHub Actions workflow](../.github/workflows/python-314t-wheels.yml)
builds **x86-64 Windows** and **x86-64 glibc Linux (manylinux 2.28+)** wheels.
It uses CPython **3.14t**, not regular CPython 3.14, and emits platform-specific
`cp314-cp314t` wheels. This workflow deliberately does **not** upload anything
to PyPI and does not invoke the upstream release automation.

## Running the complete pipeline

- **Author / GitHub Actions:** open **Actions -> CPython 3.14t wheels
  (Windows and Linux x64) -> Run workflow** and select a branch.
- **Command line:** `gh workflow run python-314t-wheels.yml --ref main`
  (after merging this branch).
- Changes to the Rust/Python bindings and related build files on `main`
  automatically trigger a build. Pull requests to `main` are also built.

Both jobs must succeed. Each wheel is checked for `cp314-cp314t`, installed
from `dist` using `--no-index`, imported in the no-GIL interpreter,
tested for read/write persistence and concurrent operations, and run through
the existing `test` unittest suite. The pipeline **fails closed** on any error.

The final `rocksdict-python-314t-x64-complete` Actions artifact contains
both tested wheels plus `SHA256SUMS`. GitHub keeps artifacts for 30 days.

## Installing the artifacts

Download and unpack the combined Actions artifact. On the matching operating
system, using an actual 64-bit Python 3.14t interpreter:

```bash
python -m pip install --no-index --no-deps --find-links ./dist rocksdict
python -c "import sys,sysconfig,rocksdict; assert sysconfig.get_config_var('Py_GIL_DISABLED') == 1; assert not sys._is_gil_enabled(); print('rocksdict / no GIL OK')"
```

The `dist` directory above should be where the downloaded wheel files were
unpacked; replace it if unpacking into another directory. Check the hashes
against `SHA256SUMS` before distributing binaries.

**Compatibility:** these are not regular CPython 3.14 wheels, not abi3 wheels,
and not compatible with 32-bit Windows, Alpine/musl, or ARM64.

**Safety:** the smoke test proves import does not re-enable the GIL for this
build and exercises basic concurrent access, but it does not establish that
every RocksDict operation is safe for simultaneous use. Avoid sharing mutable
iterators, SST writers, checkpoints, and configuration objects across threads
without application-level synchronization; review additional `unsafe impl
Send/Sync` declarations and native API thread-safety before treating the
entire extension as universally safe under unconstrained concurrent use.

## CI build cache

The two build jobs maintain **independent** caches for Windows x64 and Linux
manylinux x64. All Rust objects are keyed by OS, target ABI, pinned Rust version
and Cargo manifests. The cache restores and saves:

- `.ci-cargo/registry` and `.ci-cargo/git`: downloaded crates and Git dependencies.
- `target`: compiled `.rlib` crates (including `once_cell`) **and** RocksDB
  native C/C++ objects. A compile failure or downstream test failure does not
  prevent saving successfully created intermediate outputs.
- Windows additionally caches the LLVM/Clang 21.1.3 installation and skips
  downloading/installing it after an exact cache hit.

On Linux, `CARGO_HOME` remains at the container default (`/root/.cargo`)
so the `rustup` launcher stays available. Only its `registry` and `git`
subdirectories are bind-mounted from the host workspace. `CARGO_TARGET_DIR`
points into that same shared workspace for Rust/C++ build outputs.
On Windows the default `~/.cargo/registry` and `~/.cargo/git` are cached.
The cache is restored before Maturin starts and saved even after failed tests.

The **first run fills the cache** and still compiles `once_cell` and RocksDB.
A warm cache saves the work on subsequent compatible runs, provided the
dependency/compiler profile and native toolchain have not changed. Compiler
versions, build flags, Cargo lockfile updates, or cache eviction may trigger
recompilation. Do not share compiled objects across operating systems.

External checkout/submodule downloads, the manylinux Docker image pull, and
container-installed system RPM packages are not in this Cargo cache. Caching
these multi-gigabyte images via GitHub's artifact cache would be expensive and
fragile; a separately maintained prebuilt image is the appropriate solution
if they become the dominant cost. The Python installer itself is managed by
`actions/setup-python` using the hosted tool cache.
