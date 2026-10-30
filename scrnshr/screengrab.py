"""抓取当前桌面并打成一帧画面消息。"""

from __future__ import annotations

import ctypes

from scrnshr.viewport import encode_screen

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def capture_message(seq: int) -> dict:
    from PIL import ImageGrab

    image = ImageGrab.grab(all_screens=True)
    origin_x, origin_y, screen_w, screen_h = _virtual_screen()
    if (image.width, image.height) != (screen_w, screen_h):
        origin_x, origin_y = 0, 0
        screen_w, screen_h = image.width, image.height
    return encode_screen(image, origin_x, origin_y, screen_w, screen_h, seq)


def _virtual_screen() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)),
    )
