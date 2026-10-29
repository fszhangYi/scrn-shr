"""控制端到被控端的一条连接。"""

from __future__ import annotations

import socket
import threading

from scrnshr.auth import proof
from scrnshr.errors import AuthError, BusyError, ConnectionClosed, LanError, ProtocolError
from scrnshr.netutil import enable_tcp_keepalive, is_lan_ip
from scrnshr.protocol import PROTOCOL_VERSION, read_one, send_msg


class ClientSession:
    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._buf = bytearray()
        self._closed = True
        self._send_lock = threading.Lock()

    def connect(self, host: str, port: int, password: str) -> None:
        host = host.strip()
        if not is_lan_ip(host):
            raise LanError("只能连接局域网 IP 地址")
        sock = socket.create_connection((host, port), timeout=5)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            enable_tcp_keepalive(sock)
            sock.settimeout(5)
            buffer = bytearray()
            first = read_one(sock, buffer)
            if first.get("t") == "deny":
                raise _deny_error(first)
            if first.get("t") != "hello" or first.get("v") != PROTOCOL_VERSION:
                raise ProtocolError("对方版本不匹配")
            nonce = first.get("nonce")
            if not isinstance(nonce, str) or not nonce:
                raise ProtocolError("对方没有提供校验信息")
            send_msg(sock, {"t": "auth", "v": PROTOCOL_VERSION, "proof": proof(password, nonce)})
            reply = read_one(sock, buffer)
            if reply.get("t") == "deny":
                raise _deny_error(reply)
            if reply.get("t") != "ok":
                raise ProtocolError("连接失败")
            sock.settimeout(None)
        except Exception:
            _close_socket(sock)
            raise
        self._sock = sock
        self._buf = buffer
        self._closed = False

    def start_watch(self, on_closed) -> None:
        sock = self._sock
        buffer = self._buf

        def loop() -> None:
            try:
                while True:
                    with self._send_lock:
                        if self._closed or sock is None:
                            return
                    message = read_one(sock, buffer)
                    if message.get("t") == "bye":
                        break
            except (ConnectionClosed, ProtocolError, OSError, TimeoutError):
                pass
            should_notify = False
            with self._send_lock:
                if not self._closed:
                    self._closed = True
                    self._sock = None
                    should_notify = True
            if sock is not None:
                _close_socket(sock)
            if should_notify:
                on_closed()

        threading.Thread(target=loop, name="scrnshr-watch", daemon=True).start()

    def send(self, message: dict) -> None:
        with self._send_lock:
            sock = self._sock
            if sock is None or self._closed:
                raise ConnectionClosed("连接已断开")
            send_msg(sock, message)

    def close(self) -> None:
        with self._send_lock:
            if self._closed:
                return
            self._closed = True
            sock = self._sock
            self._sock = None
        if sock is None:
            return
        try:
            send_msg(sock, {"t": "release_all"})
            send_msg(sock, {"t": "bye"})
        except OSError:
            pass
        _close_socket(sock)


def _deny_error(message: dict) -> Exception:
    reason = message.get("reason")
    if reason == "auth":
        return AuthError("密码不正确")
    if reason == "busy":
        return BusyError("对方正在被另一台电脑控制")
    if reason == "lan":
        return LanError("对方拒绝了这个地址")
    if reason == "version":
        return ProtocolError("对方版本不匹配")
    return ProtocolError("连接被拒绝")


def _close_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
