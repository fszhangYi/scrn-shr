import pathfix  # noqa: F401

import unittest

from scrnshr.clipboard_sync import ClipboardSync


class ClipboardSyncTests(unittest.TestCase):
    def test_text_is_sent_once_until_it_changes(self):
        sync = ClipboardSync()
        first = sync.consider_text("alpha")
        self.assertEqual(first["text"], "alpha")
        self.assertIsNone(sync.consider_text("alpha"))
        second = sync.consider_text("beta")
        self.assertEqual(second["text"], "beta")

    def test_remote_text_is_not_sent_back(self):
        sync = ClipboardSync()
        applied = sync.apply({"t": "clipboard", "kind": "text", "text": "from-peer"})
        self.assertEqual(applied, ("text", "from-peer"))
        self.assertIsNone(sync.consider_text("from-peer"))

    def test_same_size_image_is_not_sent_again(self):
        sync = ClipboardSync()
        first = sync.consider_image(20, 10, b"jpeg-a")
        self.assertEqual(first["kind"], "image")
        self.assertIsNone(sync.consider_image(20, 10, b"jpeg-b"))
        changed = sync.consider_image(21, 10, b"jpeg-c")
        self.assertEqual(changed["w"], 21)

    def test_applied_image_blocks_the_echo(self):
        sync = ClipboardSync()
        applied = sync.apply({"t": "clipboard", "kind": "image", "w": 8, "h": 4, "jpg": "aGVsbG8="})
        self.assertEqual(applied[0], "image")
        self.assertIsNone(sync.consider_image(8, 4, b"hello"))


if __name__ == "__main__":
    unittest.main()
