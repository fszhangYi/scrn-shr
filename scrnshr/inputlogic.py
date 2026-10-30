"""决定哪些本地按键要转发，以及如何把窗口里的鼠标位移换成增量。"""

from __future__ import annotations

_CTRL_NAMES = frozenset({"ctrl", "ctrl_l", "ctrl_r"})
_ALT_NAMES = frozenset({"alt", "alt_l", "alt_r", "alt_gr"})
_CTRL_VK = frozenset({0x11, 0xA2, 0xA3})
_ALT_VK = frozenset({0x12, 0xA4, 0xA5})
_VK_Q = 0x51
_VK_H = 0x48
_VK_ESCAPE = 0x1B


class ForwardPolicy:
    """Ctrl+Alt+Q 断开，Ctrl+Alt+H 切换本机窗口边框，Esc 只释放光标。这些组合本身不转发出去。"""

    def __init__(self) -> None:
        self._ctrl = 0
        self._alt = 0

    def decide(self, spec: dict, down: bool) -> str:
        self._track(spec, down)
        if down and _is_escape(spec):
            return "unlock"
        if down and self._ctrl > 0 and self._alt > 0 and _is_h(spec):
            return "chrome"
        if down and self._ctrl > 0 and self._alt > 0 and _is_q(spec):
            return "disconnect"
        return "forward"

    def _track(self, spec: dict, down: bool) -> None:
        if _matches(spec, _CTRL_NAMES, _CTRL_VK):
            self._ctrl = self._ctrl + 1 if down else max(0, self._ctrl - 1)
        elif _matches(spec, _ALT_NAMES, _ALT_VK):
            self._alt = self._alt + 1 if down else max(0, self._alt - 1)


class PointerLockMath:
    """把相对窗口中心的位移变成增量，并丢掉回到中心的那一次。

    在光标真正回到中心之前不输出，避免刚锁定时把一大段跳跃发给对方。
    """

    def __init__(self) -> None:
        self._armed = False
        self._skip = False

    def disarm(self) -> None:
        self._armed = False
        self._skip = False

    def arm(self) -> None:
        if self._armed:
            return
        self._armed = True
        self._skip = True

    @property
    def armed(self) -> bool:
        return self._armed

    def on_move(self, x: int, y: int, width: int, height: int) -> tuple[int, int] | None:
        if width <= 0 or height <= 0:
            return None
        dx = int(x) - width // 2
        dy = int(y) - height // 2
        if not self._armed:
            if abs(dx) <= 3 and abs(dy) <= 3:
                self._armed = True
            return None
        if self._skip:
            self._skip = False
            return None
        if dx == 0 and dy == 0:
            return None
        self._skip = True
        return dx, dy


def _matches(spec: dict, names: frozenset[str], vks: frozenset[int]) -> bool:
    kind = spec.get("kind")
    value = spec.get("v")
    if kind == "key" and value in names:
        return True
    return kind == "vk" and value in vks


def _is_escape(spec: dict) -> bool:
    return (spec.get("kind") == "key" and spec.get("v") == "esc") or (
        spec.get("kind") == "vk" and spec.get("v") == _VK_ESCAPE
    )


def _is_h(spec: dict) -> bool:
    if spec.get("kind") == "char" and isinstance(spec.get("v"), str) and spec["v"].lower() == "h":
        return True
    return spec.get("kind") == "vk" and spec.get("v") == _VK_H


def _is_q(spec: dict) -> bool:
    if spec.get("kind") == "char" and isinstance(spec.get("v"), str) and spec["v"].lower() == "q":
        return True
    return spec.get("kind") == "vk" and spec.get("v") == _VK_Q
