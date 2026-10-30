"""被控端的打包入口。分析器靠这些导入把键鼠、托盘和截图放进 exe。"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pack.support import launch, prepare_dlls

prepare_dlls()

import PIL.Image  # noqa: F401
import PIL.ImageDraw  # noqa: F401
import PIL.ImageGrab  # noqa: F401
import PIL.ImageTk  # noqa: F401
import pynput.keyboard._win32  # noqa: F401
import pynput.mouse._win32  # noqa: F401
import pystray._win32  # noqa: F401

from scrnshr.host_app import run


def main() -> int:
    return launch(run)


if __name__ == "__main__":
    raise SystemExit(main())
