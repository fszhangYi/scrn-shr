import pathfix  # noqa: F401

import tempfile
import unittest
from pathlib import Path

from scrnshr.clipfiles import collect_files


class CollectFilesTests(unittest.TestCase):
    def test_directory_is_flattened_and_oversized_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            folder = root / "notes"
            folder.mkdir()
            (folder / "a.txt").write_text("hello", encoding="utf-8")
            nested = folder / "inner"
            nested.mkdir()
            (nested / "b.txt").write_text("world", encoding="utf-8")
            (root / "big.bin").write_bytes(b"x" * 32)
            chosen, note = collect_files([folder, root / "big.bin"], limit_bytes=16, limit_count=10)
            names = sorted(path.name for path in chosen)
            self.assertEqual(names, ["a.txt", "b.txt"])
            self.assertIn("没有全部复制", note or "")


if __name__ == "__main__":
    unittest.main()
