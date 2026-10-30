"""从剪贴板读写文件列表。只复制文件本身，目录会展开，不保留文件夹结构。"""

from __future__ import annotations

import struct
from pathlib import Path

from scrnshr.fileshare import MAX_FILE_BYTES

_CF_HDROP = 15
_LIMIT_COUNT = 40


def collect_files(paths, limit_bytes: int = MAX_FILE_BYTES, limit_count: int = _LIMIT_COUNT) -> tuple[list[Path], str | None]:
    chosen: list[Path] = []
    omitted = 0

    def add(path: Path) -> None:
        nonlocal omitted
        if len(chosen) >= limit_count:
            omitted += 1
            return
        try:
            size = path.stat().st_size
        except OSError:
            omitted += 1
            return
        if not path.is_file() or size > limit_bytes:
            omitted += 1
            return
        chosen.append(path)

    for raw in paths:
        path = Path(raw)
        try:
            is_dir = path.is_dir()
            is_file = path.is_file()
        except OSError:
            omitted += 1
            continue
        if is_file:
            add(path)
        elif is_dir:
            for child in path.rglob("*"):
                if len(chosen) >= limit_count:
                    omitted += 1
                    break
                if child.is_file():
                    add(child)
    if not chosen:
        return [], "剪贴板里没有可以复制的文件"
    if omitted:
        return chosen, "有些文件太大、太多或无法读取，没有全部复制"
    return chosen, None


def clipboard_sequence() -> int:
    import ctypes

    return int(ctypes.windll.user32.GetClipboardSequenceNumber())


def read_hdrop() -> list[str]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    if not user32.OpenClipboard(None):
        return []
    try:
        handle = user32.GetClipboardData(_CF_HDROP)
        if not handle:
            return []
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        buffer = ctypes.create_unicode_buffer(32768)
        paths = []
        for index in range(int(count)):
            length = shell32.DragQueryFileW(handle, index, buffer, len(buffer))
            if length:
                paths.append(buffer.value)
        return paths
    finally:
        user32.CloseClipboard()


def write_hdrop(paths: list[str]) -> None:
    import ctypes
    from ctypes import wintypes

    text = "\0".join(paths) + "\0\0"
    payload = struct.pack("<IiiII", 20, 0, 0, 0, 1) + text.encode("utf-16le")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.EmptyClipboard.argtypes = []
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    if not user32.OpenClipboard(None):
        raise OSError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(payload))
        if not handle:
            raise OSError("无法分配剪贴板内存")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise OSError("无法锁定剪贴板内存")
        ctypes.memmove(locked, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(_CF_HDROP, handle):
            kernel32.GlobalFree(handle)
            raise OSError("无法写入文件剪贴板")
    finally:
        user32.CloseClipboard()
