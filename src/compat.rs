//! Compatibility bridge for rust-rocksdb 0.53 / native RocksDB 11.8.1.
//!
//! This deliberately avoids relying on the private layout of the Rust wrapper.
//! Its raw-pointer access is restricted to the upstream `raw-ptr` feature.
//! Column-family handles are resolved through a live, refcounted DB on access,
//! rather than storing borrowed handles with fabricated 'static lifetimes.

use librocksdb_sys as ffi;
use rocksdb::{AsColumnFamilyRef, AsRawPtr, DBWithThreadMode, MultiThreaded, Options};
use std::sync::Arc;

type DB = DBWithThreadMode<MultiThreaded>;

/// Strong DB reference + name: owns the database until the CF proxy is dropped.
///
/// An underlying CF must not be dropped while a proxy for it is being used.
/// The outer Python API enforces CF lifetime rules; the lookup below performs
/// a fail-fast sanity check instead of dereferencing a stale C pointer.
#[derive(Clone)]
pub(crate) struct ColumnFamilyHandle {
    db: Arc<DB>,
    name: Arc<str>,
}

impl ColumnFamilyHandle {
    pub(crate) fn new(db: Arc<DB>, name: &str) -> Option<Self> {
        // Keep the source Arc borrowed by the temporary BoundColumnFamily.
        // Clone the strong reference rather than moving a still-borrowed DB.
        db.cf_handle(name).map(|_| Self {
            db: db.clone(),
            name: Arc::from(name),
        })
    }

    pub(crate) fn name_str(&self) -> &str {
        &self.name
    }
}

impl AsColumnFamilyRef for ColumnFamilyHandle {
    fn inner(&self) -> *mut ffi::rocksdb_column_family_handle_t {
        self.db
            .cf_handle(&self.name)
            .expect("column family handle invalidated during native API use")
            .inner()
    }
}

/// Public upstream raw pointer export, instead of accessing private fields.
pub(crate) trait RawDbPtr {
    fn inner(&self) -> *mut ffi::rocksdb_t;
}
impl RawDbPtr for DB {
    fn inner(&self) -> *mut ffi::rocksdb_t {
        // SAFETY: The borrow of self keeps RocksDB's underlying DB alive.
        unsafe { AsRawPtr::as_raw_ptr(self) }
    }
}

pub(crate) trait RawOptionsPtr {
    fn inner(&self) -> *mut ffi::rocksdb_options_t;
}
impl RawOptionsPtr for Options {
    fn inner(&self) -> *mut ffi::rocksdb_options_t {
        // SAFETY: Options owns the returned pointer for the duration of &self.
        unsafe { AsRawPtr::as_raw_ptr(self) }
    }
}
