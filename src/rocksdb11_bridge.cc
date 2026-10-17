// RocksDict RocksDB 11.8.1 C++ bridge.
// The upstream rust-rocksdb 0.53.0 wrapper does not expose wide-column APIs.
// This narrow C ABI binds the native DB::GetEntity/PutEntity/Iterator::columns.
//
// IMPORTANT ABI CONTRACT: rocksdb_t, rocksdb_iterator_t, and
// rocksdb_column_family_handle_t layouts match db/c.cc in RocksDB 11.8.1.
// A compile-time version gate rejects all other native versions.
// Do not use this bridge with external/system-linked RocksDB builds without
// verifying the C API wrappers' layout and binary versions.

#include "rocksdb/c.h"
#include "rocksdb/db.h"
#include "rocksdb/iterator.h"
#include "rocksdb/options.h"
#include "rocksdb/version.h"
#include "rocksdb/wide_columns.h"
#include "rocksdb/write_batch.h"

#include <cstdlib>
#include <cstring>
#include <exception>
#include <new>
#include <string>
#include <utility>
#include <vector>

static_assert(ROCKSDB_MAJOR == 11 && ROCKSDB_MINOR == 8 && ROCKSDB_PATCH == 1,
              "RocksDict wide-column bridge requires RocksDB 11.8.1");

// Exact definitions from RocksDB 11.8.1 db/c.cc. These are C API wrappers.
struct rocksdb_t {
  rocksdb::DB* rep;
};
struct rocksdb_iterator_t {
  rocksdb::Iterator* rep;
};
struct rocksdb_writebatch_t {
  rocksdb::WriteBatch rep;
};
struct rocksdb_column_family_handle_t {
  rocksdb::ColumnFamilyHandle* rep;
  bool immortal;
};

// The first member of C API readoptions is rocksdb::ReadOptions rep.
// We don't duplicate its other internal members; we only access the first
// subobject while keeping the original options owner alive.
static const rocksdb::ReadOptions& read_options(
    const rocksdb_readoptions_t* c_options) {
  return *reinterpret_cast<const rocksdb::ReadOptions*>(c_options);
}

struct rocksdict11_columns {
  std::vector<std::pair<std::string, std::string>> data;
};

static void set_error(char** error, const std::string& message) {
  if (!error) return;
  char* copy = static_cast<char*>(std::malloc(message.size() + 1));
  if (!copy) return;
  std::memcpy(copy, message.data(), message.size());
  copy[message.size()] = '\0';
  *error = copy;
}

static rocksdict11_columns* copy_columns(
    const rocksdb::WideColumns& columns) {
  auto* result = new rocksdict11_columns;
  try {
    result->data.reserve(columns.size());
    for (const auto& column : columns) {
      result->data.emplace_back(column.name().ToString(),
                                column.value().ToString());
    }
  } catch (...) {
    delete result;
    throw;
  }
  return result;
}

extern "C" {

int rocksdict11_native_major() { return ROCKSDB_MAJOR; }
int rocksdict11_native_minor() { return ROCKSDB_MINOR; }
int rocksdict11_native_patch() { return ROCKSDB_PATCH; }

// Return: 0=found, 1=not found, -1=error.
// On success caller owns *out and must call rocksdict11_columns_free.
int rocksdict11_get_entity(
    rocksdb_t* db, const rocksdb_readoptions_t* opts,
    rocksdb_column_family_handle_t* cf, const char* key, size_t key_len,
    rocksdict11_columns** out, char** error) {
  if (out) *out = nullptr;
  if (error) *error = nullptr;
  if (!db || !db->rep || !opts || !cf || !cf->rep || !out) {
    set_error(error, "invalid RocksDB GetEntity arguments");
    return -1;
  }
  try {
    rocksdb::PinnableWideColumns columns;
    const auto status = db->rep->GetEntity(
        read_options(opts), cf->rep, rocksdb::Slice(key, key_len), &columns);
    if (status.IsNotFound()) return 1;
    if (!status.ok()) {
      set_error(error, status.ToString());
      return -1;
    }
    *out = copy_columns(columns.columns());
    return 0;
  } catch (const std::exception& exc) {
    set_error(error, exc.what());
    return -1;
  } catch (...) {
    set_error(error, "unknown exception in GetEntity");
    return -1;
  }
}

int rocksdict11_put_entity(
    rocksdb_t* db, rocksdb_column_family_handle_t* cf,
    const char* key, size_t key_len, const char* const* names,
    const size_t* name_lens, const char* const* values,
    const size_t* value_lens, size_t count, unsigned int flags, char** error) {
  if (error) *error = nullptr;
  if (!db || !db->rep || !cf || !cf->rep ||
      (count && (!names || !name_lens || !values || !value_lens))) {
    set_error(error, "invalid RocksDB PutEntity arguments");
    return -1;
  }
  try {
    rocksdb::WideColumns columns;
    columns.reserve(count);
    for (size_t i = 0; i < count; ++i) {
      columns.emplace_back(
          rocksdb::Slice(names[i], name_lens[i]),
          rocksdb::Slice(values[i], value_lens[i]));
    }
    rocksdb::WriteOptions opts;
    opts.sync = (flags & 1u) != 0;
    opts.disableWAL = (flags & 2u) != 0;
    opts.ignore_missing_column_families = (flags & 4u) != 0;
    opts.no_slowdown = (flags & 8u) != 0;
    opts.low_pri = (flags & 16u) != 0;
    opts.memtable_insert_hint_per_batch = (flags & 32u) != 0;
    auto status = db->rep->PutEntity(
        opts, cf->rep, rocksdb::Slice(key, key_len), columns);
    if (!status.ok()) {
      set_error(error, status.ToString());
      return -1;
    }
    return 0;
  } catch (const std::exception& exc) {
    set_error(error, exc.what());
    return -1;
  } catch (...) {
    set_error(error, "unknown exception in PutEntity");
    return -1;
  }
}

// Append a wide-column PutEntity operation to an existing RocksDB write batch.
// The returned status is validated by Rust before the batch is written to DB.
int rocksdict11_writebatch_put_entity(
    rocksdb_writebatch_t* batch, rocksdb_column_family_handle_t* cf,
    const char* key, size_t key_len, const char* const* names,
    const size_t* name_lens, const char* const* values,
    const size_t* value_lens, size_t count, char** error) {
  if (error) *error = nullptr;
  if (!batch || !cf || !cf->rep ||
      (count && (!names || !name_lens || !values || !value_lens))) {
    set_error(error, "invalid RocksDB WriteBatch PutEntity arguments");
    return -1;
  }
  try {
    rocksdb::WideColumns columns;
    columns.reserve(count);
    for (size_t i = 0; i < count; ++i) {
      columns.emplace_back(
          rocksdb::Slice(names[i], name_lens[i]),
          rocksdb::Slice(values[i], value_lens[i]));
    }
    auto status = batch->rep.PutEntity(
        cf->rep, rocksdb::Slice(key, key_len), columns);
    if (!status.ok()) {
      set_error(error, status.ToString());
      return -1;
    }
    return 0;
  } catch (const std::exception& exc) {
    set_error(error, exc.what());
    return -1;
  } catch (...) {
    set_error(error, "unknown exception in WriteBatch PutEntity");
    return -1;
  }
}

// C iterator's columns() is not exposed in the rust-rocksdb 0.53 wrapper.
int rocksdict11_iter_columns(
    rocksdb_iterator_t* iterator, rocksdict11_columns** out, char** error) {
  if (out) *out = nullptr;
  if (error) *error = nullptr;
  if (!iterator || !iterator->rep || !out || !iterator->rep->Valid()) {
    set_error(error, "invalid RocksDB iterator");
    return -1;
  }
  try {
    *out = copy_columns(iterator->rep->columns());
    return 0;
  } catch (const std::exception& exc) {
    set_error(error, exc.what());
    return -1;
  } catch (...) {
    set_error(error, "unknown exception reading iterator columns");
    return -1;
  }
}

size_t rocksdict11_columns_len(const rocksdict11_columns* cols) {
  return cols ? cols->data.size() : 0;
}

const char* rocksdict11_column_name(
    const rocksdict11_columns* cols, size_t i, size_t* len) {
  if (len) *len = 0;
  if (!cols || !len || i >= cols->data.size()) return nullptr;
  const auto& value = cols->data[i].first;
  *len = value.size();
  return value.data();
}

const char* rocksdict11_column_value(
    const rocksdict11_columns* cols, size_t i, size_t* len) {
  if (len) *len = 0;
  if (!cols || !len || i >= cols->data.size()) return nullptr;
  const auto& value = cols->data[i].second;
  *len = value.size();
  return value.data();
}

void rocksdict11_columns_free(rocksdict11_columns* cols) {
  delete cols;
}

}  // extern "C"
