import pathfix  # noqa: F401

import unittest
from pathlib import Path

from scrnshr.protocol import DEFERRED_TYPES
from scrnshr.scope import CLIENT_NOTES, DEFERRED_SENTENCE, HOST_NOTES, MANUAL_SENTENCE

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scrnshr"
FORBIDDEN = ("winreg", "CurrentVersion\\Run", "StartupApproved", "schtasks", "RunOnce")


class ScopeTests(unittest.TestCase):
    def test_deferred_channels_are_screen_file_and_clipboard(self):
        self.assertEqual(DEFERRED_TYPES, frozenset({"screen", "file", "clipboard"}))

    def test_both_windows_state_the_boundary(self):
        for notes in (HOST_NOTES, CLIENT_NOTES):
            text = "\n".join(notes)
            self.assertIn(DEFERRED_SENTENCE, text)
            self.assertIn(MANUAL_SENTENCE, text)
            for word in ("画面", "文件", "剪贴板", "手动", "开机"):
                self.assertIn(word, text)

    def test_apps_use_the_shared_boundary(self):
        host = (PACKAGE / "host_app.py").read_text(encoding="utf-8")
        client = (PACKAGE / "client_app.py").read_text(encoding="utf-8")
        self.assertIn("HOST_NOTES", host)
        self.assertIn("CLIENT_NOTES", client)
        self.assertIn("DEFERRED_SENTENCE", client)

    def test_package_does_not_register_autostart(self):
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for item in FORBIDDEN:
                self.assertNotIn(item, text, msg=f"{path.name} 包含 {item}")


if __name__ == "__main__":
    unittest.main()
