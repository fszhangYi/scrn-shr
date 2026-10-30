"""决定剪贴板内容要不要发给对方，并挡住刚写回去的回声。"""

from __future__ import annotations

import base64

MAX_TEXT = 200_000
MAX_IMAGE = 1_500_000


class ClipboardSync:
    def __init__(self) -> None:
        self._echo_text: str | None = None
        self._echo_image = None
        self._seq = 0

    def note_text(self, text: str | None) -> None:
        if isinstance(text, str):
            self._echo_text = text

    def note_image(self, width: int, height: int) -> None:
        self._echo_image = (int(width), int(height))

    def consider_text(self, text: str | None) -> dict | None:
        if not isinstance(text, str) or text == "" or text == self._echo_text:
            return None
        if len(text) > MAX_TEXT:
            return None
        self._echo_text = text
        self._seq += 1
        return {"t": "clipboard", "kind": "text", "seq": self._seq, "text": text}

    def consider_image(self, width: int, height: int, jpeg: bytes) -> dict | None:
        size = (int(width), int(height))
        if size == self._echo_image or not jpeg or len(jpeg) > MAX_IMAGE:
            return None
        self._echo_image = size
        self._seq += 1
        return {
            "t": "clipboard",
            "kind": "image",
            "seq": self._seq,
            "w": size[0],
            "h": size[1],
            "jpg": base64.b64encode(jpeg).decode("ascii"),
        }

    def apply(self, message: dict):
        kind = message.get("kind")
        if kind == "text":
            text = message.get("text")
            if not isinstance(text, str) or len(text) > MAX_TEXT:
                return None
            self._echo_text = text
            return ("text", text)
        if kind == "image":
            try:
                raw = base64.b64decode(message.get("jpg", ""), validate=True)
            except Exception:
                return None
            if not raw or len(raw) > MAX_IMAGE:
                return None
            width = message.get("w")
            height = message.get("h")
            if isinstance(width, int) and isinstance(height, int) and not isinstance(width, bool):
                self._echo_image = (width, height)
            return ("image", raw)
        return None
