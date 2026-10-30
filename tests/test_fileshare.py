import pathfix  # noqa: F401

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scrnshr.fileshare import IncomingFiles, OutgoingFile, safe_name


class FileShareTests(unittest.TestCase):
    def test_safe_name_keeps_only_the_file_name(self):
        self.assertEqual(safe_name(r"..\..\report.txt"), "report.txt")
        with self.assertRaises(ValueError):
            safe_name("..")
        with self.assertRaises(ValueError):
            safe_name("CON.txt")

    def test_round_trip_writes_only_inside_the_receive_directory(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "notes.txt"
            source.write_bytes("你好，文件".encode("utf-8"))
            incoming = IncomingFiles(root / "in")
            saved = None
            for message in OutgoingFile(source, "abc").messages():
                note = incoming.handle(message)
                if note and note.startswith("已保存"):
                    saved = Path(note.removeprefix("已保存 ").strip())
            self.assertIsNotNone(saved)
            self.assertEqual(saved.read_text(encoding="utf-8"), "你好，文件")
            self.assertEqual(saved.parent, root / "in")

    def test_incomplete_file_is_removed(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            incoming = IncomingFiles(root)
            incoming.handle({"t": "file_begin", "id": "1", "name": "a.bin", "size": 4})
            incoming.handle({"t": "file_abort", "id": "1"})
            self.assertEqual(list(root.iterdir()), [])

    def test_oversize_declaration_is_refused(self):
        with TemporaryDirectory() as raw:
            incoming = IncomingFiles(Path(raw))
            note = incoming.handle({"t": "file_begin", "id": "1", "name": "a.bin", "size": 201 * 1024 * 1024})
            self.assertIn("无法接收", note)


if __name__ == "__main__":
    unittest.main()
