"""把收到的动作变成 Windows 上的键盘和鼠标输入。"""

from __future__ import annotations


def parse_key(spec: dict):
    from pynput.keyboard import Key, KeyCode

    kind = spec.get("kind")
    value = spec.get("v")
    if kind == "char" and isinstance(value, str) and len(value) == 1:
        return KeyCode.from_char(value)
    if kind == "vk" and isinstance(value, int):
        return KeyCode.from_vk(value)
    if kind == "key" and isinstance(value, str):
        try:
            return Key[value]
        except KeyError:
            return None
    return None


class PynputInjector:
    """按下和松开成对记录，断开时全部松开。"""

    def __init__(self, mouse=None, keyboard=None) -> None:
        if mouse is None or keyboard is None:
            from pynput.keyboard import Controller as Keyboard
            from pynput.mouse import Controller as Mouse

            mouse = Mouse() if mouse is None else mouse
            keyboard = Keyboard() if keyboard is None else keyboard
        self._mouse = mouse
        self._keyboard = keyboard
        self._held_buttons: list[str] = []
        self._held_keys: list[tuple] = []

    def move(self, dx: int, dy: int) -> None:
        try:
            self._mouse.move(int(dx), int(dy))
        except Exception:
            return

    def move_abs(self, x: int, y: int) -> None:
        try:
            self._mouse.position = (int(x), int(y))
        except Exception:
            return

    def button(self, name: str, down: bool) -> None:
        button = _button(name)
        if button is None:
            return
        try:
            if down:
                self._mouse.press(button)
                if name not in self._held_buttons:
                    self._held_buttons.append(name)
            else:
                self._mouse.release(button)
                if name in self._held_buttons:
                    self._held_buttons.remove(name)
        except Exception:
            return

    def scroll(self, dx: int, dy: int) -> None:
        try:
            self._mouse.scroll(int(dx), int(dy))
        except Exception:
            return

    def key(self, spec: dict, down: bool) -> None:
        key = parse_key(spec)
        if key is None:
            return
        token = (spec["kind"], spec["v"])
        try:
            if down:
                self._keyboard.press(key)
                if token not in self._held_keys:
                    self._held_keys.append(token)
            else:
                self._keyboard.release(key)
                if token in self._held_keys:
                    self._held_keys.remove(token)
        except Exception:
            return

    def release_all(self) -> None:
        for name in list(self._held_buttons):
            button = _button(name)
            if button is None:
                continue
            try:
                self._mouse.release(button)
            except Exception:
                pass
        self._held_buttons.clear()
        for kind, value in reversed(self._held_keys):
            key = parse_key({"kind": kind, "v": value})
            if key is None:
                continue
            try:
                self._keyboard.release(key)
            except Exception:
                pass
        self._held_keys.clear()


def _button(name: str):
    from pynput.mouse import Button

    return getattr(Button, name, None)
