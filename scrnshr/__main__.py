"""命令入口。"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write("用法:\n  python -m scrnshr host\n  python -m scrnshr client\n")
        return 0
    if sys.platform != "win32":
        sys.stderr.write("这一版只支持 Windows。\n")
        return 2
    commands = {
        "host": "scrnshr.host_app",
        "client": "scrnshr.client_app",
    }
    module_name = commands.get(args[0])
    if module_name is None:
        sys.stderr.write("未知命令。可用: host、client\n")
        return 2
    from importlib import import_module

    try:
        import_module(module_name).run()
    except Exception as exc:
        _report(exc)
        return 1
    return 0


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            pass


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
