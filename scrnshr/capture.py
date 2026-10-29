"""控制端在 Windows 上锁定光标、捕获键盘。"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes


class _RECT(ctypes.Structure):
    _fields_ = (
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    )


def clip_cursor(left: int, top: int, right: int, bottom: int) -> None:
    rect = _RECT(int(left), int(top), int(right), int(bottom))
    if not ctypes.windll.user32.ClipCursor(ctypes.byref(rect)):
        raise OSError("无法把光标限制在控制窗口里")


def release_cursor_clip() -> None:
    ctypes.windll.user32.ClipCursor(None)


def set_cursor_pos(x: int, y: int) -> None:
    if not ctypes.windll.user32.SetCursorPos(int(x), int(y)):
        raise OSError("无法把光标移回窗口中心")


def spec_from_pynput(key) -> dict | None:
    from pynput.keyboard import Key, KeyCode

    if isinstance(key, Key):
        return {"kind": "key", "v": key.name}
    if isinstance(key, KeyCode):
        if key.vk is not None:
            return {"kind": "vk", "v": int(key.vk)}
        char = key.char
        if isinstance(char, str) and len(char) == 1 and ord(char) >= 32:
            return {"kind": "char", "v": char}
    return None


class KeyHook:
    """吞掉本机键盘事件，改交给回调。停止时恢复本机键盘。"""

    def __init__(self, on_event) -> None:
        self._on_event = on_event
        self._listener = None

    def start(self) -> None:
        from pynput.keyboard import Listener

        self._listener = Listener(
            on_press=self._press,
            on_release=self._release,
            suppress=True,
        )
        self._listener.start()
        if not _wait_ready(self._listener, 2.0):
            self.stop()
            raise RuntimeError("键盘捕获没有启动")

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def _press(self, key) -> None:
        spec = spec_from_pynput(key)
        if spec is not None:
            self._on_event(spec, True)

    def _release(self, key) -> None:
        spec = spec_from_pynput(key)
        if spec is not None:
            self._on_event(spec, False)


def _wait_ready(listener, timeout: float) -> bool:
    ready = threading.Event()

    def waiter() -> None:
        try:
            listener.wait()
        finally:
            ready.set()

    threading.Thread(target=waiter, name="scrnshr-key-ready", daemon=True).start()
    return ready.wait(timeout)
