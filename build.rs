// Build only the small compatibility bridge against the exact native headers
// exported by rust-librocksdb-sys 0.48.1+11.8.1.
//
// DEP_ROCKSDB_INCLUDE comes from that crate's links = "rocksdb" metadata.
// We intentionally do not download sources or compile RocksDB a second time.

use std::env;
use std::path::Path;

fn main() {
    let include_dir = env::var("DEP_ROCKSDB_INCLUDE")
        .expect("rust-librocksdb-sys did not export DEP_ROCKSDB_INCLUDE");
    if !Path::new(&include_dir).join("rocksdb/version.h").is_file() {
        panic!("Invalid RocksDB native include directory: {include_dir}");
    }
    println!("cargo:rerun-if-changed=src/rocksdb11_bridge.cc");
    println!("cargo:rerun-if-env-changed=DEP_ROCKSDB_INCLUDE");
    // RocksDB 11.8.1 exposes defaulted comparisons and scoped enum imports
    // requiring C++20. cc-rs/clang-cl otherwise defaults to exceptions OFF
    // on Windows, but our C ABI bridge catches C++ exceptions and turns them
    // into Python-visible error statuses.
    let mut bridge = cc::Build::new();
    bridge
        .cpp(true)
        .std("c++20")
        .include(&include_dir)
        .file("src/rocksdb11_bridge.cc")
        .warnings(false);
    if env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        bridge.flag("/EHsc");
    }
    bridge.compile("rocksdict_rocksdb11_bridge");
}
