"""命令入口。"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write("用法:\n  python -m scrnshr host\n")
        return 0
    if sys.platform != "win32":
        sys.stderr.write("这一版只支持 Windows。\n")
        return 2
    if args[0] != "host":
        sys.stderr.write("未知命令。当前可用: host\n")
        return 2
    from scrnshr.host_app import run

    try:
        run()
    except Exception as exc:
        _report(exc)
        return 1
    return 0


def _report(exc: BaseException) -> None:
    text = str(exc) or exc.__class__.__name__
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("局域网键鼠", text)
        root.destroy()
    except Exception:
        sys.stderr.write(text + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
