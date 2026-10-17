"""Integration acceptance gates for native RocksDB 11.8.1 and CPython 3.14t.

These tests exercise the new C++ wide-column bridge and are deliberately
not run until the migration is ready for a controlled build attempt.
"""

import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

from rocksdict import FlushOptions, Options, Rdict, native_rocksdb_version


class RocksDB11Integration(unittest.TestCase):
    def test_native_version_and_nogil(self):
        self.assertEqual(native_rocksdb_version(), (11, 8, 1))
        self.assertEqual(sys.version_info[:2], (3, 14))
        self.assertEqual(sysconfig.get_config_var("Py_GIL_DISABLED"), 1)
        self.assertFalse(sys._is_gil_enabled())

    def test_empty_raw_key_and_invalid_iterator_position(self):
        with tempfile.TemporaryDirectory(prefix="rd11-emptykey-") as folder:
            db_path = str(Path(folder) / "db")
            db = Rdict(db_path, Options(raw_mode=True))
            try:
                db[b""] = b""
                db[b"nonempty"] = b"ok"
                it = db.iter()
                self.assertFalse(it.valid())
                self.assertIsNone(it.key())
                self.assertIsNone(it.value())
                it.seek_to_first()
                self.assertEqual(it.key(), b"")
                self.assertEqual(it.value(), b"")
                it.next()
                self.assertEqual(it.key(), b"nonempty")
                self.assertEqual(it.value(), b"ok")
            finally:
                db.close()
            Rdict.destroy(db_path)

    def test_invalid_legacy_ttl_rejected(self):
        from rocksdict import AccessType
        # Python -> u64 validation occurs before Duration construction.
        with self.assertRaises((OverflowError, ValueError)):
            AccessType.with_ttl(-1)

    def test_native_11_ingest_option_controls(self):
        from rocksdict import IngestExternalFileOptions
        options = IngestExternalFileOptions()
        options.set_file_opening_threads(4)
        options.set_failed_move_fall_back_to_copy(True)
        options.set_allow_db_generated_files(True)
        options.set_fill_cache(False)
        options.set_link_files(False)
        options.set_prefetch_lmax_index_and_filter_blocks(True)
        options.set_verify_checksums_before_ingest(True)
        options.set_verify_checksums_readahead_size(256 * 1024)
        options.set_verify_file_checksum(True)
        options.set_write_global_seqno(True)
        options.set_fail_if_not_bottommost_level(True)
        with self.assertRaisesRegex(Exception, "file_opening_threads"):
            options.set_file_opening_threads(0)

    def test_native_11_options(self):
        opts = Options(raw_mode=True)
        opts.set_read_io_executor_threads(2)
        self.assertEqual(opts.get_read_io_executor_threads(), 2)
        opts.set_avoid_unnecessary_blocking_io(True)
        flush = FlushOptions()
        self.assertFalse(flush.listener_wait)
        flush.listener_wait = True
        self.assertTrue(flush.listener_wait)

    def test_wide_columns_roundtrip_and_iteration(self):
        with tempfile.TemporaryDirectory(prefix="rd11-columns-") as folder:
            db_path = str(Path(folder) / "db")
            db = Rdict(db_path, Options(raw_mode=True))
            try:
                db.put_entity(
                    b"record1",
                    [b"", b"color", b"size"],
                    [b"original", b"blue", b"42"],
                )
                expected = [(b"", b"original"), (b"color", b"blue"), (b"size", b"42")]
                self.assertEqual(db.get_entity(b"record1"), expected)
                self.assertIsNone(db.get_entity(b"missing"))
                # Native iterator::columns() is a distinct API from DB::GetEntity.
                rows = list(db.entities())
                self.assertEqual(rows, [(b"record1", expected)])
            finally:
                db.close()
            db = Rdict(db_path, Options(raw_mode=True))
            try:
                self.assertEqual(
                    db.get_entity(b"record1"),
                    [(b"", b"original"), (b"color", b"blue"), (b"size", b"42")],
                )
            finally:
                db.close()
            Rdict.destroy(db_path)

    def test_iterator_outlives_python_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="rd11-snapiter-") as folder:
            db_path = str(Path(folder) / "db")
            db = Rdict(db_path, Options(raw_mode=True))
            try:
                db[b"before"] = b"old"
                snap = db.snapshot()
                iterator = snap.items()
                del snap  # Native snapshot must remain owned by iterator.
                db[b"before"] = b"new"
                self.assertEqual(list(iterator), [(b"before", b"old")])
                del iterator
            finally:
                db.close()
            Rdict.destroy(db_path)

    def test_invalid_wide_column_order_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="rd11-invalid-columns-") as folder:
            path = str(Path(folder) / "db")
            db = Rdict(path, Options(raw_mode=True))
            try:
                with self.assertRaises(Exception) as invalid_order:
                    db.put_entity(b"order", [b"z", b"a"], [b"first", b"second"])
                self.assertIn("sorted", str(invalid_order.exception))
                with self.assertRaises(Exception):
                    db.put_entity(b"duplicate", [b"same", b"same"], [b"1", b"2"])
                with self.assertRaises(Exception):
                    db.put_entity(b"empty", [], [])
                self.assertIsNone(db.get_entity(b"order"))
                db[b"plain"] = b"payload"
                self.assertEqual(db.get_entity(b"plain"), [(b"", b"payload")])
            finally:
                db.close()
            Rdict.destroy(path)

    def test_cf_handle_survives_family_drop_without_use_after_free(self):
        with tempfile.TemporaryDirectory(prefix="rd11-dropped-cf-") as folder:
            path = str(Path(folder) / "db")
            opts = Options(raw_mode=True)
            opts.create_if_missing(True)
            opts.create_missing_column_families(True)
            db = Rdict(path, opts)
            try:
                db.create_column_family("temporary", Options(raw_mode=True)).close()
                handle = db.get_column_family_handle("temporary")
                db.drop_column_family("temporary")
                # The wrapper must not free C CF handle while Python still owns it.
                del handle
            finally:
                db.close()
            Rdict.destroy(path)

    def test_verify_native_file_checksums(self):
        with tempfile.TemporaryDirectory(prefix="rd11-checksums-") as folder:
            path = str(Path(folder) / "db")
            db = Rdict(path, Options(raw_mode=True))
            try:
                db[b"key"] = b"value"
                db.flush()
                db.verify_file_checksums()
            finally:
                db.close()
            Rdict.destroy(path)

    def test_column_family_options_reload(self):
        with tempfile.TemporaryDirectory(prefix="rd11-cf-") as folder:
            path = str(Path(folder) / "db")
            opts = Options(raw_mode=True)
            opts.create_if_missing(True)
            opts.create_missing_column_families(True)
            db = Rdict(path, opts)
            try:
                cf = db.create_column_family("data", Options(raw_mode=True))
                cf[b"hello"] = b"world"
                cf.close()
            finally:
                db.close()
            loaded, columns = Options.load_latest(path)
            self.assertIn("data", columns)
            self.assertTrue(isinstance(loaded, Options))
            reopened = Rdict(path)
            try:
                self.assertEqual(reopened.get_column_family("data")[b"hello"], b"world")
            finally:
                reopened.close()
            Rdict.destroy(path)

    def test_wide_column_write_batch_is_atomic(self):
        from rocksdict import WriteBatch
        with tempfile.TemporaryDirectory(prefix="rd11-wb-entity-") as folder:
            path = str(Path(folder) / "db")
            db = Rdict(path, Options(raw_mode=True))
            try:
                wb = WriteBatch(raw_mode=True)
                wb.set_default_column_family(db.get_column_family_handle("default"))
                wb.put_entity(b"entity", [b"", b"color"], [b"one", b"green"])
                wb.put(b"plain", b"two")
                db.write(wb)
                self.assertEqual(db.get_entity(b"entity"), [(b"", b"one"), (b"color", b"green")])
                self.assertEqual(db[b"plain"], b"two")
                with self.assertRaises(Exception):
                    wb.put(b"after", b"consumed")
            finally:
                db.close()
            Rdict.destroy(path)

    def test_read_snapshot_is_stable(self):
        with tempfile.TemporaryDirectory(prefix="rd11-snapshot-") as folder:
            path = str(Path(folder) / "db")
            db = Rdict(path, Options(raw_mode=True))
            try:
                db[b"k"] = b"before"
                snap = db.snapshot()
                try:
                    db[b"k"] = b"after"
                    self.assertEqual(snap[b"k"], b"before")
                    self.assertEqual(db[b"k"], b"after")
                    self.assertEqual(list(snap.items()), [(b"k", b"before")])
                finally:
                    del snap
            finally:
                db.close()
            Rdict.destroy(path)


if __name__ == "__main__":
    unittest.main()
