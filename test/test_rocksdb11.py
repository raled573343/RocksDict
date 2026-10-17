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
