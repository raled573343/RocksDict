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
    cc::Build::new()
        .cpp(true)
        .std("c++17")
        .include(&include_dir)
        .file("src/rocksdb11_bridge.cc")
        .warnings(false)
        .compile("rocksdict_rocksdb11_bridge");
}
