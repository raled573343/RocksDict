//! C ABI wrappers for RocksDB 11.8.1 native entity APIs.
//!
//! The new Rust wrapper does not expose wide columns. All buffers are copied
//! into owned Rust allocations before native column buffers are released.
//! C++ exceptions are caught by the bridge; only C ABI status codes cross FFI.

use crate::compat::{ColumnFamilyHandle, RawDbPtr};
use crate::options::ReadOpt;
use crate::util::error_message;
use libc::{c_char, c_int, c_uint, size_t};
use pyo3::exceptions::PyException;
use pyo3::{PyErr, PyResult};
use rocksdb::{AsColumnFamilyRef, DBWithThreadMode, MultiThreaded};
use std::ptr::null_mut;

type DB = DBWithThreadMode<MultiThreaded>;

#[repr(C)]
struct NativeColumns {
    _opaque: [u8; 0],
}

unsafe extern "C" {
    fn rocksdict11_native_major() -> c_int;
    fn rocksdict11_native_minor() -> c_int;
    fn rocksdict11_native_patch() -> c_int;

    fn rocksdict11_get_entity(
        db: *mut librocksdb_sys::rocksdb_t,
        opts: *const librocksdb_sys::rocksdb_readoptions_t,
        cf: *mut librocksdb_sys::rocksdb_column_family_handle_t,
        key: *const c_char,
        key_len: size_t,
        out: *mut *mut NativeColumns,
        err: *mut *mut c_char,
    ) -> c_int;
    fn rocksdict11_put_entity(
        db: *mut librocksdb_sys::rocksdb_t,
        cf: *mut librocksdb_sys::rocksdb_column_family_handle_t,
        key: *const c_char,
        key_len: size_t,
        names: *const *const c_char,
        name_lens: *const size_t,
        values: *const *const c_char,
        value_lens: *const size_t,
        count: size_t,
        flags: c_uint,
        err: *mut *mut c_char,
    ) -> c_int;
    fn rocksdict11_iter_columns(
        iterator: *mut librocksdb_sys::rocksdb_iterator_t,
        out: *mut *mut NativeColumns,
        err: *mut *mut c_char,
    ) -> c_int;
    fn rocksdict11_columns_len(cols: *const NativeColumns) -> size_t;
    fn rocksdict11_column_name(cols: *const NativeColumns, i: size_t, len: *mut size_t) -> *const c_char;
    fn rocksdict11_column_value(cols: *const NativeColumns, i: size_t, len: *mut size_t) -> *const c_char;
    fn rocksdict11_columns_free(cols: *mut NativeColumns);
}

struct OwnedColumns(*mut NativeColumns);

impl Drop for OwnedColumns {
    fn drop(&mut self) {
        unsafe { rocksdict11_columns_free(self.0) }
    }
}

fn take_columns(ptr: *mut NativeColumns) -> PyResult<Vec<(Vec<u8>, Vec<u8>)>> {
    if ptr.is_null() {
        return Err(PyException::new_err("RocksDB native wide-column handle was null"));
    }
    let columns = OwnedColumns(ptr);
    let count = unsafe { rocksdict11_columns_len(columns.0) };
    let mut result = Vec::with_capacity(count);
    for i in 0..count {
        let mut n_len: size_t = 0;
        let mut v_len: size_t = 0;
        let (n, v) = unsafe {
            (
                rocksdict11_column_name(columns.0, i, &mut n_len),
                rocksdict11_column_value(columns.0, i, &mut v_len),
            )
        };
        if n.is_null() || v.is_null() {
            return Err(PyException::new_err("RocksDB returned invalid native column"));
        }
        let n_bytes = unsafe { std::slice::from_raw_parts(n as *const u8, n_len) };
        let v_bytes = unsafe { std::slice::from_raw_parts(v as *const u8, v_len) };
        result.push((n_bytes.to_vec(), v_bytes.to_vec()));
    }
    Ok(result)
}

fn native_error(err: *mut c_char, context: &'static str) -> PyErr {
    if err.is_null() {
        PyException::new_err(context)
    } else {
        PyException::new_err(error_message(err))
    }
}

pub(crate) fn native_version() -> (i32, i32, i32) {
    unsafe {
        (
            rocksdict11_native_major(),
            rocksdict11_native_minor(),
            rocksdict11_native_patch(),
        )
    }
}

pub(crate) fn get_entity(
    db: &DB,
    cf: &ColumnFamilyHandle,
    opts: &ReadOpt,
    key: &[u8],
) -> PyResult<Option<Vec<(Vec<u8>, Vec<u8>)>>> {
    let mut data = null_mut();
    let mut err = null_mut();
    let status = unsafe {
        rocksdict11_get_entity(
            db.inner(),
            opts.0,
            cf.inner(),
            key.as_ptr() as *const c_char,
            key.len(),
            &mut data,
            &mut err,
        )
    };
    match status {
        0 => Ok(Some(take_columns(data)?)),
        1 => Ok(None),
        _ => Err(native_error(err, "RocksDB native GetEntity failed")),
    }
}

pub(crate) fn put_entity(
    db: &DB,
    cf: &ColumnFamilyHandle,
    key: &[u8],
    names: &[Vec<u8>],
    values: &[Vec<u8>],
    flags: u32,
) -> PyResult<()> {
    if names.len() != values.len() {
        return Err(PyException::new_err("column names and values must have equal lengths"));
    }
    let n_ptrs: Vec<*const c_char> = names.iter().map(|s| s.as_ptr() as *const c_char).collect();
    let v_ptrs: Vec<*const c_char> = values.iter().map(|s| s.as_ptr() as *const c_char).collect();
    let n_lens: Vec<size_t> = names.iter().map(Vec::len).collect();
    let v_lens: Vec<size_t> = values.iter().map(Vec::len).collect();
    let mut err = null_mut();
    let status = unsafe {
        rocksdict11_put_entity(
            db.inner(),
            cf.inner(),
            key.as_ptr() as *const c_char,
            key.len(),
            n_ptrs.as_ptr(),
            n_lens.as_ptr(),
            v_ptrs.as_ptr(),
            v_lens.as_ptr(),
            names.len(),
            flags,
            &mut err,
        )
    };
    if status == 0 {
        Ok(())
    } else {
        Err(native_error(err, "RocksDB native PutEntity failed"))
    }
}

pub(crate) fn iterator_columns(
    raw_iter: *mut librocksdb_sys::rocksdb_iterator_t,
) -> PyResult<Vec<(Vec<u8>, Vec<u8>)>> {
    let mut data = null_mut();
    let mut err = null_mut();
    let status = unsafe { rocksdict11_iter_columns(raw_iter, &mut data, &mut err) };
    if status == 0 {
        take_columns(data)
    } else {
        Err(native_error(err, "RocksDB iterator columns failed"))
    }
}
