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

/// An owned native CF handle plus its owning database.
///
/// The CF Arc is dropped before the DB Arc. Both are required: the Rust
/// wrapper may remove a dropped CF from its map while other Python objects
/// still reference its C handle.
#[derive(Clone)]
pub(crate) struct ColumnFamilyHandle {
    cf: rocksdb::OwnedColumnFamily,
    _db: Arc<DB>,
}

impl ColumnFamilyHandle {
    pub(crate) fn new(db: Arc<DB>, name: &str) -> Option<Self> {
        db.cf_handle_owned(name).map(|cf| Self {
            cf,
            _db: db.clone(),
        })
    }
}

impl AsColumnFamilyRef for ColumnFamilyHandle {
    fn inner(&self) -> *mut ffi::rocksdb_column_family_handle_t {
        self.cf.inner()
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
