"""窗口和托盘共用的小工具。"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def configure_root(root: tk.Tk) -> None:
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass


def place_window(root: tk.Misc, width: int, height: int) -> None:
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")


def make_icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(37, 99, 168, 255))
    draw.rounded_rectangle((16, 14, 48, 38), radius=3, outline=(255, 255, 255, 255), width=3)
    draw.polygon([(28, 36), (34, 36), (40, 52), (26, 48)], fill=(255, 255, 255, 255))
    return image
