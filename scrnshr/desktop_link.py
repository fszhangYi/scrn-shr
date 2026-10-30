"""两端共用的文件收发和剪贴板轮询。"""

from __future__ import annotations

import io
import threading
from pathlib import Path

from scrnshr.clipboard_sync import ClipboardSync
from scrnshr.fileshare import IncomingFiles, OutgoingFile, default_receive_dir


class DesktopLink:
    def __init__(self, root, send, on_status, directory: Path | None = None) -> None:
        self.root = root
        self._send = send
        self._on_status = on_status
        self.files = IncomingFiles(directory or default_receive_dir())
        self.sync = ClipboardSync()
        self._polling = False
        self._ticks = 0
        self._sending = False
        self._after_id = None

    def start(self) -> None:
        self.sync.note_text(_read_text(self.root))
        image = _read_image()
        if image is not None:
            self.sync.note_image(image.width, image.height)
        self._polling = True
        self._schedule()

    def stop(self) -> None:
        self._polling = False
        self._cancel()
        self.files.abort_all()

    def handle(self, message: dict) -> None:
        kind = message.get("t")
        if kind in {"file_begin", "file_chunk", "file_end", "file_abort"}:
            note = self.files.handle(message)
            if note:
                self._on_status(note)
            return
        if kind != "clipboard":
            return
        applied = self.sync.apply(message)
        if applied is None:
            return
        mode, payload = applied
        if mode == "text":
            _write_text(self.root, payload)
            self._on_status("已更新剪贴板文字")
            return
        if _write_image(payload):
            self._on_status("已更新剪贴板图片")
        else:
            self._on_status("对方发来了图片，但没有写入剪贴板")

    def send_path(self, path: Path) -> None:
        if self._sending:
            self._on_status("上一个文件还在发送")
            return
        self._sending = True
        threading.Thread(target=self._send_worker, args=(Path(path),), name="scrnshr-file", daemon=True).start()

    def _send_worker(self, path: Path) -> None:
        try:
            outgoing = OutgoingFile(path)
            total = max(1, outgoing.size)
            sent = 0
            self._status(f"正在发送 {outgoing.name}")
            for message in outgoing.messages():
                if message["t"] == "file_chunk":
                    import base64

                    sent += len(base64.b64decode(message["data"]))
                    self._status(f"正在发送 {outgoing.name} {min(100, int(sent * 100 / total))}%")
                self._send(message)
            self._status(f"已发送 {outgoing.name}")
        except Exception as exc:
            self._status(f"发送失败：{exc}")
        finally:
            self._sending = False

    def _cancel(self) -> None:
        after_id = self._after_id
        self._after_id = None
        if after_id is None:
            return
        try:
            self.root.after_cancel(after_id)
        except Exception:
            pass

    def _schedule(self) -> None:
        try:
            self._after_id = self.root.after(400, self._poll)
        except Exception:
            self._polling = False

    def _poll(self) -> None:
        self._after_id = None
        if not self._polling:
            return
        try:
            text_message = self.sync.consider_text(_read_text(self.root))
            if text_message is not None:
                self._send(text_message)
            self._ticks += 1
            if self._ticks % 3 == 0:
                image = _read_image()
                if image is not None:
                    jpeg = _jpeg_bytes(image)
                    image_message = self.sync.consider_image(image.width, image.height, jpeg)
                    if image_message is not None:
                        self._send(image_message)
        except Exception:
            pass
        if self._polling:
            self._schedule()

    def _status(self, text: str) -> None:
        try:
            self.root.after(0, lambda: self._on_status(text))
        except Exception:
            pass


def _read_text(root) -> str | None:
    try:
        return root.clipboard_get()
    except Exception:
        return None


def _write_text(root, text: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(text)


def _read_image():
    try:
        from PIL import Image, ImageGrab
    except Exception:
        return None
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(data, Image.Image):
        return data
    return None


def _jpeg_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def _write_image(raw: bytes) -> bool:
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw))
        image.load()
        _set_dib(image.convert("RGB"))
        return True
    except Exception:
        return False


def _set_dib(image) -> None:
    import ctypes
    from ctypes import wintypes

    buffer = io.BytesIO()
    image.save(buffer, "BMP")
    dib = buffer.getvalue()[14:]
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    if not user32.OpenClipboard(None):
        raise OSError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(dib))
        if not handle:
            raise OSError("无法分配剪贴板内存")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise OSError("无法锁定剪贴板内存")
        ctypes.memmove(locked, dib, len(dib))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(8, handle):
            kernel32.GlobalFree(handle)
            raise OSError("无法写入剪贴板图片")
    finally:
        user32.CloseClipboard()
