"""抓取当前桌面。有变化才编码，优先用更快的桌面复制。"""

from __future__ import annotations

import ctypes
import time

from scrnshr.viewport import encode_screen, plan_frame

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def capture_message(seq: int) -> dict:
    image, origin_x, origin_y, screen_w, screen_h = _grab_image()
    return encode_screen(image, origin_x, origin_y, screen_w, screen_h, seq)


class ScreenPump:
    """记住上一帧。画面没变就不产生消息，避免占住和键鼠共用的发送。"""

    def __init__(self) -> None:
        self._previous = None
        self._candidate = None
        self._full = False
        self._last_full = 0.0
        self._mss = None
        self._mss_failed = False

    def close(self) -> None:
        grabber = self._mss
        self._mss = None
        if grabber is not None:
            try:
                grabber.close()
            except Exception:
                pass

    def prepare(self, seq: int) -> dict | None:
        image, origin_x, origin_y, screen_w, screen_h = self._grab()
        force_full = self._previous is not None and time.perf_counter() - self._last_full > 2.0
        message, commit = plan_frame(
            self._previous,
            image,
            origin_x,
            origin_y,
            screen_w,
            screen_h,
            seq,
            force_full=force_full,
        )
        self._candidate = commit if message is not None else None
        self._full = message is not None and message.get("cx") is None
        return message

    def commit(self) -> None:
        if self._candidate is not None:
            self._previous = self._candidate
            self._candidate = None
        if self._full:
            self._last_full = time.perf_counter()
            self._full = False

    def _grab(self):
        if not self._mss_failed:
            try:
                return self._grab_fast()
            except Exception:
                self._mss_failed = True
                self.close()
        return _grab_image()

    def _grab_fast(self):
        if self._mss is None:
            import mss

            self._mss = mss.mss()
        monitor = self._mss.monitors[0]
        shot = self._mss.grab(monitor)
        from PIL import Image

        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        origin_x = int(monitor["left"])
        origin_y = int(monitor["top"])
        screen_w = int(monitor["width"])
        screen_h = int(monitor["height"])
        if image.size != (screen_w, screen_h):
            return image, 0, 0, image.width, image.height
        return image, origin_x, origin_y, screen_w, screen_h


def _grab_image():
    from PIL import ImageGrab

    image = ImageGrab.grab(all_screens=True)
    origin_x, origin_y, screen_w, screen_h = _virtual_screen()
    if (image.width, image.height) != (screen_w, screen_h):
        return image, 0, 0, image.width, image.height
    return image, origin_x, origin_y, screen_w, screen_h


def _virtual_screen() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)),
    )
