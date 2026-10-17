# Automatic RocksDict CPython 3.14t releases

The workflow [auto-release-314t.yml](../.github/workflows/auto-release-314t.yml)
checks new upstream stable versions **daily at 04:17 UTC**, and supports manual
`workflow_dispatch`. GitHub cron execution can be delayed.

## Version discovery and publication

The source of truth is **upstream GitHub Releases**, `rocksdict/RocksDict`.
Only published stable tags in the form `vMAJOR.MINOR.PATCH` qualify;
prereleases, drafts and bare main-branch commits are excluded.

- **Bootstrap version 0.3.29** is published from the already tested
  [Actions run #39024425551](https://github.com/raled573343/RocksDict/actions/runs/39024425551).
  It does **not** rerun the Rust/C++ compiler or Maturin.
- For later versions, the workflow chooses the **oldest missing** stable
  upstream version after 0.3.29, builds it once for two platforms and
  publishes one GitHub Release. If several versions arrive, at most **one**
  new version is handled per daily run.
- When all eligible versions already have complete GitHub Releases, the
  discover job exits; **no compilation runner is started**.
- A complete release is recognized only if its assets include both expected
  wheel tags and `SHA256SUMS`.

Releases are named `cp314t-v<version>` (for example `cp314t-v0.3.29`)
and contain:

- `rocksdict-<version>-cp314-cp314t-win_amd64.whl`;
- `rocksdict-<version>-cp314-cp314t-manylinux_2_28_x86_64.whl`;
- `SHA256SUMS`.

**Never publishes to PyPI.** The pre-existing `.github/workflows/CI.yml`
release jobs explicitly skip `cp314t-v*` tags, avoiding any old all-platform
compilation or PyPI upload caused by publishing GitHub Releases.

## Upstream source and safety gates

For a new version the builder checks out the exact upstream release tag's
**resolved Git commit SHA**, including native Git submodules. The checkout
must match that SHA, and `pyproject.toml`, `Cargo.toml` and `Cargo.lock`
must agree on the version. CI applies the fork's required PyO3 free-threaded
module declaration and conservative mutable native-object method signatures.

Builds **fail closed** on incompatible upstream API changes (or unsupported
PyO3), rather than publishing an incorrectly tagged wheel. When a new
upstream version changes those APIs, update `tools/auto_release_314t.py`
and retest its adaptations.

Each wheel must pass: a real CPython 3.14t runtime check with GIL off; a
`cp314-cp314t` wheel metadata check; offline install from `dist`; import
without re-enabling GIL; multi-threaded write/read and persistence test;
and the upstream Python unittest suite.

The release stage starts **only if both OS jobs pass** and is scoped to
`contents: write` and `actions: read`; builders have read-only
permissions. Release creation is first staged as a draft and published after
all assets are uploaded. A failed draft upload can be resumed. A
workflow-wide concurrency lock prevents two scheduled/manual release runs
from racing.

## Avoiding rebuilds and downloading dependencies

The standalone `python-314t-wheels.yml` workflow is now **manual / PR**
only. The old main-branch push trigger was removed so changing these
workflows does not perform another expensive full native rebuild.
Clippy remains available for PRs and its existing scheduled analysis,
rather than every main-branch push.

On a no-new-version day, only a GitHub API check runs. Bootstrap reuses
existing signed-off CI artifacts. A truly new upstream source version is
compiled and tested before it can appear in Releases.

Native Rust/RocksDB compilation, Cargo registry/git downloads, Windows
LLVM/Clang and Linux Rust/RPM packages are cached separately by OS/ABI and
version/source commit where appropriate. Manylinux Docker image downloading
still happens on GitHub-hosted runners; avoiding it requires a persistent
runner or prebuilt image infrastructure.

## Operation

To manually check: GitHub -> **Actions -> Daily upstream RocksDict cp314t
releases -> Run workflow**. If the version already has a complete release,
nothing is rebuilt.

Published binaries: https://github.com/raled573343/RocksDict/releases

A failed build should be diagnosed from the `discover`, `wheels`,
and `release` jobs; never manually retag an untested wheel.
