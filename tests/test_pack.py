import pathfix  # noqa: F401

import unittest
from pathlib import Path

from datetime import datetime

from pack.build_exe import (
    TARGETS,
    is_blocked_binary,
    is_conda_prefix,
    output_name,
    pyinstaller_args,
    spec_source,
    tk_binaries,
)
from pack.support import RUNTIME_DLLS, imported_dll_names

ROOT = Path(__file__).resolve().parents[1]


class PackScriptTests(unittest.TestCase):
    def test_each_side_has_its_own_script_and_exe_name(self):
        host_bat = (ROOT / "打包被控端.bat").read_text(encoding="utf-8")
        client_bat = (ROOT / "打包控制端.bat").read_text(encoding="utf-8")
        self.assertIn("pack\\build_exe.py host", host_bat)
        self.assertIn("pack\\build_exe.py client", client_bat)
        self.assertIn("build\\packvenv\\Scripts\\python.exe", host_bat)
        self.assertIn("build\\packvenv\\Scripts\\python.exe", client_bat)
        self.assertNotIn(".venv\\Scripts\\python.exe", host_bat)
        self.assertNotIn(".venv\\Scripts\\python.exe", client_bat)
        self.assertNotIn("build_exe.py client", host_bat)
        self.assertNotIn("build_exe.py host", client_bat)

        host_args = pyinstaller_args("host", ROOT)
        client_args = pyinstaller_args("client", ROOT)
        self.assertIn("--onefile", host_args)
        self.assertIn("--windowed", host_args)
        self.assertIn(TARGETS["host"]["name"], host_args)
        self.assertIn(TARGETS["client"]["name"], client_args)
        self.assertIn("pystray._win32", host_args)
        self.assertNotIn("pystray._win32", client_args)
        self.assertTrue(str(host_args[-1]).endswith("host_entry.py"))
        self.assertTrue(str(client_args[-1]).endswith("client_entry.py"))
        bundled = " ".join(tk_binaries()).lower()
        self.assertTrue("tcl90.dll" in bundled or "tcl86t.dll" in bundled)
        self.assertTrue("tcl9tk90.dll" in bundled or "tk86t.dll" in bundled)
        self.assertIn("vcruntime140_1.dll", bundled)
        if "tcl90.dll" in bundled:
            self.assertIn("libtommath.dll", bundled)
        if "tcl86t.dll" in bundled:
            self.assertIn("zlib1.dll", bundled)
            self.assertNotIn("miniconda", bundled)
            self.assertNotIn("anaconda", bundled)
        self.assertTrue(is_blocked_binary("api-ms-win-crt-runtime-l1-1-0.dll"))
        self.assertTrue(is_blocked_binary("ucrtbase.dll"))
        self.assertFalse(is_blocked_binary("tcl90.dll"))
        for kind in ("host", "client"):
            source = spec_source(kind, ROOT)
            self.assertIn("api-ms-win-", source)
            self.assertIn("upx=False", source)
            lower = source.lower()
            self.assertTrue("tcl90.dll" in lower or "tcl86t.dll" in lower)
            if "tcl86t.dll" in lower:
                self.assertIn("zlib1.dll", lower)
                self.assertNotIn("miniconda", lower)
            self.assertIn("rthook_dll.py", source)
        stamped = output_name("client", datetime(2026, 10, 30, 9, 49, 12))
        self.assertEqual(stamped, "局域网键鼠控制端-20261030-094912")
        self.assertIn(stamped, spec_source("client", ROOT, stamped))
        self.assertTrue(is_conda_prefix(r"C:\Users\user\miniconda3"))
        self.assertFalse(is_conda_prefix(str(ROOT / "build" / "cpython")))
        names = [item.lower() for item in imported_dll_names(Path(__import__("_tkinter").__file__))]
        self.assertTrue(any(item.startswith("tcl") and item.endswith(".dll") for item in names))
        self.assertIn("tcl86t.dll", RUNTIME_DLLS)
        self.assertIn("tcl90.dll", RUNTIME_DLLS)
        client_entry = (ROOT / "pack" / "client_entry.py").read_text(encoding="utf-8")
        self.assertLess(client_entry.index("prepare_dlls()"), client_entry.index("import PIL.ImageTk"))

    def test_entries_do_not_request_admin_or_autostart(self):
        forbidden = ("winreg", "schtasks", "uac-admin", "requireAdministrator")
        for path in (ROOT / "pack").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for item in forbidden:
                self.assertNotIn(item, text, msg=f"{path.name} 包含 {item}")


if __name__ == "__main__":
    unittest.main()
