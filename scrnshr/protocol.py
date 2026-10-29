"""长度前缀加 JSON 的小协议。

一条消息只描述一次键盘或鼠标动作。画面、文件和剪贴板不走这里，
单条消息也限制在 64KB，放不下这些内容。
"""

from __future__ import annotations

import json
import socket
import struct

from scrnshr.errors import ConnectionClosed, ProtocolError

PROTOCOL_VERSION = 1
MAX_MESSAGE = 64 * 1024
DEFERRED_TYPES = frozenset({"screen", "file", "clipboard"})
_HEADER = struct.Struct(">I")


def pack(message: dict) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_MESSAGE:
        raise ProtocolError("消息过长")
    return _HEADER.pack(len(payload)) + payload


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
            chunk = sock.recv(8192)
        except socket.timeout as exc:
            raise TimeoutError("等待对方响应超时") from exc
        if not chunk:
            raise ConnectionClosed("连接已断开")
        buffer.extend(chunk)
