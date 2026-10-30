"""长度前缀加 JSON。键鼠、画面、文件分片和剪贴板都走这一条连接。"""

from __future__ import annotations

import json
import socket
import struct

from scrnshr.errors import ConnectionClosed, ProtocolError

PROTOCOL_VERSION = 1
MAX_MESSAGE = 4 * 1024 * 1024
_HEADER = struct.Struct(">I")


def pack(message: dict) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_MESSAGE:
        raise ProtocolError("消息过长")
    return _HEADER.pack(len(payload)) + payload


_SCREEN_PREFIX = b"SCRN"
_SCREEN_HEAD = struct.Struct("<BBIhhHHHHHHHH")


def pack_screen(message: dict) -> bytes:
    """画面走二进制，不再套 Base64。键鼠消息仍是 JSON，可以插在两帧之间。"""
    jpg = message.get("jpg")
    if isinstance(jpg, str):
        import base64

        jpg = base64.b64decode(jpg)
    if not isinstance(jpg, (bytes, bytearray)) or not jpg:
        raise ProtocolError("画面为空")
    cropped = message.get("cx") is not None
    body = _SCREEN_PREFIX + _SCREEN_HEAD.pack(
        1 if cropped else 0,
        0,
        int(message.get("seq", 0)) & 0xFFFFFFFF,
        int(message["ox"]),
        int(message["oy"]),
        int(message["sw"]),
        int(message["sh"]),
        int(message["w"]),
        int(message["h"]),
        int(message.get("cx", 0)),
        int(message.get("cy", 0)),
        int(message.get("cw", 0)),
        int(message.get("ch", 0)),
    ) + bytes(jpg)
    if len(body) > MAX_MESSAGE:
        raise ProtocolError("消息过长")
    return _HEADER.pack(len(body)) + body


def _unpack_screen(body: bytes) -> dict:
    need = len(_SCREEN_PREFIX) + _SCREEN_HEAD.size
    if len(body) < need or not body.startswith(_SCREEN_PREFIX):
        raise ProtocolError("画面无法解析")
    flags, _pad, seq, ox, oy, sw, sh, width, height, cx, cy, cw, ch = _SCREEN_HEAD.unpack_from(body, len(_SCREEN_PREFIX))
    jpg = body[need:]
    if not jpg or sw <= 0 or sh <= 0 or width <= 0 or height <= 0:
        raise ProtocolError("画面无法解析")
    message = {"t": "screen", "seq": seq, "ox": ox, "oy": oy, "sw": sw, "sh": sh, "w": width, "h": height, "jpg": jpg}
    if flags & 1:
        message.update(cx=cx, cy=cy, cw=cw, ch=ch)
    return message


def pop_message(buffer: bytearray) -> dict | None:
    if len(buffer) < _HEADER.size:
        return None
    (length,) = _HEADER.unpack(buffer[: _HEADER.size])
    if length <= 0 or length > MAX_MESSAGE:
        raise ProtocolError("消息长度不合法")
    total = _HEADER.size + length
    if len(buffer) < total:
        return None
    raw = bytes(buffer[_HEADER.size : total])
    del buffer[:total]
    if raw.startswith(_SCREEN_PREFIX):
        return _unpack_screen(raw)
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("消息无法解析") from exc
    if not isinstance(message, dict):
        raise ProtocolError("消息格式不正确")
    return message


def send_msg(sock: socket.socket, message: dict) -> None:
    sock.sendall(pack(message))


def read_one(sock: socket.socket, buffer: bytearray) -> dict:
    while True:
        message = pop_message(buffer)
        if message is not None:
            return message
        try:
            chunk = sock.recv(65536)
        except socket.timeout as exc:
            raise TimeoutError("等待对方响应超时") from exc
        if not chunk:
            raise ConnectionClosed("连接已断开")
        buffer.extend(chunk)
