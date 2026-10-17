use crate::db_reference::{DbReference, DbReferenceHolder};
use crate::encoder::{decode_value, encode_key};
use crate::exceptions::DbClosedError;
use crate::{Rdict, RdictItems, RdictIter, RdictKeys, RdictValues, ReadOptionsPy};
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use crate::compat::{ColumnFamilyHandle, RawDbPtr};
use crate::options::ReadOpt;
use crate::util::error_message;
use rocksdb::AsColumnFamilyRef;
use libc::{c_char, size_t};
use std::ptr::null_mut;

/// A consistent view of the database at the point of creation.
///
/// Examples:
///     ::
///
///         from rocksdict import Rdict
///
///         db = Rdict("tmp")
///         for i in range(100):
///             db[i] = i
///
///         # take a snapshot
///         snapshot = db.snapshot()
///
///         for i in range(90):
///             del db[i]
///
///         # 0-89 are no longer in db
///         for k, v in db.items():
///             print(f"{k} -> {v}")
///
///         # but they are still in the snapshot
///         for i in range(100):
///             assert snapshot[i] == i
///
///         # drop the snapshot
///         del snapshot, db
///
///         Rdict.destroy("tmp")
#[pyclass]
pub struct Snapshot {
    pub(crate) inner: *const librocksdb_sys::rocksdb_snapshot_t,
    pub(crate) column_family: Option<ColumnFamilyHandle>,
    pub(crate) pickle_loads: Py<PyAny>,
    pub(crate) read_opt: ReadOpt,
    // decrease db Rc last
    pub(crate) db: DbReferenceHolder,
    pub(crate) raw_mode: bool,
}

#[pymethods]
impl Snapshot {
    /// Creates an iterator over the data in this snapshot under the given column family, using
    /// the default read options.
    ///
    /// Args:
    ///     read_opt: ReadOptions, must have the same `raw_mode` argument.
    #[pyo3(signature = (read_opt = None))]
    fn iter(&self, read_opt: Option<&ReadOptionsPy>, py: Python) -> PyResult<RdictIter> {
        let read_opt: ReadOptionsPy = match read_opt {
            None => ReadOptionsPy::default(py)?,
            Some(opt) => opt.clone(),
        };
        RdictIter::new_with_snapshot(
            &self.db,
            &self.column_family,
            read_opt,
            &self.pickle_loads,
            self.raw_mode,
            py,
            Some(self.inner),
        )
    }

    /// Iterate through all keys and values pairs.
    ///
    /// Args:
    ///     backwards: iteration direction, forward if `False`.
    ///     from_key: iterate from key, first seek to this key
    ///         or the nearest next key for iteration
    ///         (depending on iteration direction).
    ///     read_opt: ReadOptions, must have the same `raw_mode` argument.
    #[pyo3(signature = (backwards = false, from_key = None, read_opt = None))]
    fn items(
        &self,
        backwards: bool,
        from_key: Option<&Bound<PyAny>>,
        read_opt: Option<&ReadOptionsPy>,
        py: Python,
    ) -> PyResult<RdictItems> {
        RdictItems::new(self.iter(read_opt, py)?, backwards, from_key)
    }

    /// Iterate through all keys.
    ///
    /// Args:
    ///     backwards: iteration direction, forward if `False`.
    ///     from_key: iterate from key, first seek to this key
    ///         or the nearest next key for iteration
    ///         (depending on iteration direction).
    ///     read_opt: ReadOptions, must have the same `raw_mode` argument.
    #[pyo3(signature = (backwards = false, from_key = None, read_opt = None))]
    fn keys(
        &self,
        backwards: bool,
        from_key: Option<&Bound<PyAny>>,
        read_opt: Option<&ReadOptionsPy>,
        py: Python,
    ) -> PyResult<RdictKeys> {
        RdictKeys::new(self.iter(read_opt, py)?, backwards, from_key)
    }

    /// Iterate through all values.
    ///
    /// Args:
    ///     backwards: iteration direction, forward if `False`.
    ///     from_key: iterate from key, first seek to this key
    ///         or the nearest next key for iteration
    ///         (depending on iteration direction).
    ///     read_opt: ReadOptions, must have the same `raw_mode` argument.
    #[pyo3(signature = (backwards = false, from_key = None, read_opt = None))]
    fn values(
        &self,
        backwards: bool,
        from_key: Option<&Bound<PyAny>>,
        read_opt: Option<&ReadOptionsPy>,
        py: Python,
    ) -> PyResult<RdictValues> {
        RdictValues::new(self.iter(read_opt, py)?, backwards, from_key)
    }

    /// read from snapshot
    fn __getitem__<'py>(&self, key: &Bound<PyAny>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let key = encode_key(key, self.raw_mode)?;
        let db = self.get_db();
        let mut value_len: size_t = 0;
        let mut err: *mut c_char = null_mut();
        // Native RocksDB 11 owns the returned allocation, which must be freed
        // using rocksdb_free after we decode/copy its contents.
        let value = unsafe {
            match &self.column_family {
                Some(cf) => librocksdb_sys::rocksdb_get_cf(
                    db.inner(),
                    self.read_opt.0,
                    cf.inner(),
                    key.as_ptr() as *const c_char,
                    key.len(),
                    &mut value_len,
                    &mut err,
                ),
                None => librocksdb_sys::rocksdb_get(
                    db.inner(),
                    self.read_opt.0,
                    key.as_ptr() as *const c_char,
                    key.len(),
                    &mut value_len,
                    &mut err,
                ),
            }
        };
        if !err.is_null() {
            if !value.is_null() {
                unsafe { librocksdb_sys::rocksdb_free(value.cast()) };
            }
            return Err(PyException::new_err(error_message(err)));
        }
        if value.is_null() {
            return Err(PyException::new_err("key not found"));
        }
        let decoded = unsafe {
            let bytes = std::slice::from_raw_parts(value as *const u8, value_len);
            decode_value(py, bytes, &self.pickle_loads, self.raw_mode)
        };
        unsafe { librocksdb_sys::rocksdb_free(value.cast()) };
        decoded
    }
}

impl Snapshot {
    pub(crate) fn new(rdict: &Rdict, py: Python) -> PyResult<Self> {
        let db_inner = rdict
            .db
            .get()
            .ok_or_else(|| DbClosedError::new_err("DB instance already closed"))?
            .inner();
        let snapshot = unsafe { librocksdb_sys::rocksdb_create_snapshot(db_inner) };
        let r_opt: ReadOpt = rdict
            .read_opt_py
            .to_read_opt(rdict.opt_py.raw_mode, py)?;
        unsafe {
            set_snapshot(r_opt.0, snapshot);
        }
        Ok(Snapshot {
            inner: snapshot,
            column_family: rdict.column_family.clone(),
            pickle_loads: rdict.loads.clone(),
            read_opt: r_opt,
            db: rdict.db.clone(),
            raw_mode: rdict.opt_py.raw_mode,
        })
    }

    fn get_db(&self) -> &DbReference {
        self.db
            .get()
            .expect("Snapshot should never close its DbReference")
    }
}

impl Drop for Snapshot {
    fn drop(&mut self) {
        unsafe {
            librocksdb_sys::rocksdb_release_snapshot(self.get_db().inner(), self.inner);
        }
    }
}

/// `Send` and `Sync` implementations for `SnapshotWithThreadMode` are safe, because `SnapshotWithThreadMode` is
/// immutable and can be safely shared between threads.
unsafe impl Send for Snapshot {}
unsafe impl Sync for Snapshot {}

#[inline]
pub(crate) unsafe fn set_snapshot(
    read_opt: *mut librocksdb_sys::rocksdb_readoptions_t,
    snapshot_inner: *const librocksdb_sys::rocksdb_snapshot_t,
) {
    librocksdb_sys::rocksdb_readoptions_set_snapshot(read_opt, snapshot_inner);
}
