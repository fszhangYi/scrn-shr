import pathfix  # noqa: F401

import unittest
from pathlib import Path

from scrnshr.scope import CLIENT_NOTES, HOST_NOTES, MANUAL_SENTENCE, SAVE_SENTENCE, SHARE_SENTENCE

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scrnshr"
FORBIDDEN = ("winreg", "CurrentVersion\\Run", "StartupApproved", "schtasks", "RunOnce")


class ScopeTests(unittest.TestCase):
    def test_both_windows_describe_screen_files_and_clipboard(self):
        for notes in (HOST_NOTES, CLIENT_NOTES):
            text = "\n".join(notes)
            self.assertIn(SHARE_SENTENCE, text)
            self.assertIn(MANUAL_SENTENCE, text)
            self.assertIn(SAVE_SENTENCE, text)
            for word in ("画面", "文件", "剪贴板", "手动", "开机"):
                self.assertIn(word, text)

    def test_apps_expose_the_channels(self):
        host = (PACKAGE / "host_app.py").read_text(encoding="utf-8")
        client = (PACKAGE / "client_app.py").read_text(encoding="utf-8")
        self.assertIn("发送文件", host)
        self.assertIn("capture_message", host)
        self.assertIn("发送文件", client)
        self.assertIn("decode_screen", client)

    def test_package_does_not_register_autostart(self):
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for item in FORBIDDEN:
                self.assertNotIn(item, text, msg=f"{path.name} 包含 {item}")


if __name__ == "__main__":
    unittest.main()
