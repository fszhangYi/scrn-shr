"""把一个文件拆成若干条消息，接收端只写到指定目录里。"""

from __future__ import annotations

import base64
import secrets
from pathlib import Path

MAX_FILE_BYTES = 200 * 1024 * 1024
CHUNK_RAW = 192 * 1024
_RESERVED = {"CON", "PRN", "AUX", "NUL"}


def default_receive_dir() -> Path:
    home = Path.home()
    downloads = home / "Downloads"
    root = downloads if downloads.is_dir() else home
    target = root / "局域网键鼠"
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_name(name: str) -> str:
    base = Path(str(name)).name.strip().rstrip(". ")
    if not base or base in {".", ".."}:
        raise ValueError("文件名不合法")
    if any(char in base for char in '<>:"/\\|?*'):
        raise ValueError("文件名不合法")
    stem = Path(base).stem.upper()
    if stem in _RESERVED or (_device_name(stem)):
        raise ValueError("文件名不合法")
    return base


def _device_name(stem: str) -> bool:
    for prefix in ("COM", "LPT"):
        if stem.startswith(prefix) and stem[len(prefix):].isdigit():
            return True
    return False


def unique_path(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("同名文件太多")


class OutgoingFile:
    def __init__(self, path: Path, transfer_id: str | None = None) -> None:
        self.path = Path(path)
        self.name = safe_name(self.path.name)
        self.size = self.path.stat().st_size
        if self.size > MAX_FILE_BYTES:
            raise ValueError("文件超过 200MB")
        self.transfer_id = transfer_id or secrets.token_hex(8)

    def messages(self):
        yield {"t": "file_begin", "id": self.transfer_id, "name": self.name, "size": self.size}
        index = 0
        with self.path.open("rb") as handle:
            while True:
                blob = handle.read(CHUNK_RAW)
                if not blob:
                    break
                yield {
                    "t": "file_chunk",
                    "id": self.transfer_id,
                    "i": index,
                    "data": base64.b64encode(blob).decode("ascii"),
                }
                index += 1
        yield {"t": "file_end", "id": self.transfer_id}


class IncomingFiles:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._open: dict[str, dict] = {}
        self._clip_paths: list[Path] = []

    def handle(self, message: dict) -> str | None:
        kind = message.get("t")
        transfer_id = message.get("id")
        if not isinstance(transfer_id, str) or not transfer_id:
            return "文件消息缺少编号"
        if kind == "file_begin":
            return self._begin(transfer_id, message)
        if kind == "file_chunk":
            return self._chunk(transfer_id, message)
        if kind == "file_end":
            return self._end(transfer_id, message)
        if kind == "file_abort":
            self._discard(transfer_id)
            return "对方取消了文件传输"
        return None

    def abort_all(self) -> None:
        for transfer_id in list(self._open):
            self._discard(transfer_id)

    def _begin(self, transfer_id: str, message: dict) -> str:
        self._discard(transfer_id)
        try:
            name = safe_name(str(message.get("name", "")))
            size = message.get("size")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
                raise ValueError("文件大小不正确")
            path = unique_path(self.directory, name)
            handle = path.open("wb")
        except (OSError, ValueError) as exc:
            return f"无法接收文件：{exc}"
        self._open[transfer_id] = {
            "handle": handle,
            "path": path,
            "size": size,
            "got": 0,
            "next": 0,
            "name": name,
            "clip": message.get("clip") is True,
        }
        return f"正在接收 {name}"

    def _chunk(self, transfer_id: str, message: dict) -> str | None:
        slot = self._open.get(transfer_id)
        if slot is None:
            return "收到了未知的文件分片"
        index = message.get("i")
        if isinstance(index, bool) or not isinstance(index, int) or index != slot["next"]:
            self._discard(transfer_id)
            return "文件分片顺序不正确，已取消"
        try:
            blob = base64.b64decode(message.get("data", ""), validate=True)
        except Exception:
            self._discard(transfer_id)
            return "文件分片无法解析，已取消"
        if slot["got"] + len(blob) > slot["size"]:
            self._discard(transfer_id)
            return "文件比声明的更大，已取消"
        try:
            slot["handle"].write(blob)
        except OSError as exc:
            self._discard(transfer_id)
            return f"写入失败：{exc}"
        slot["got"] += len(blob)
        slot["next"] += 1
        if slot["size"] == 0:
            return None
        percent = int(slot["got"] * 100 / slot["size"])
        return f"正在接收 {slot['name']} {percent}%"

    def _end(self, transfer_id: str, _message: dict) -> str:
        slot = self._open.get(transfer_id)
        if slot is None:
            return "文件还没开始接收"
        if slot["got"] != slot["size"]:
            self._discard(transfer_id)
            return "文件不完整，已取消"
        path = slot["path"]
        self._close_handle(slot)
        del self._open[transfer_id]
        if slot.get("clip"):
            self._clip_paths.append(path)
        return f"已保存 {path}"

    def take_clip_paths(self) -> list[Path]:
        paths = self._clip_paths
        self._clip_paths = []
        return paths

    def _discard(self, transfer_id: str) -> None:
        slot = self._open.pop(transfer_id, None)
        if slot is None:
            return
        self._close_handle(slot)
        try:
            slot["path"].unlink(missing_ok=True)
        except OSError:
            pass

    def _close_handle(self, slot: dict) -> None:
        try:
            slot["handle"].close()
        except OSError:
            pass
