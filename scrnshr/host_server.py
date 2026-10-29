"""被控端：在局域网里等待一个控制端，并把动作交给注入器。"""

from __future__ import annotations

import socket
import sys
import threading

from scrnshr.auth import new_nonce, verify
from scrnshr.errors import AuthError, BindError, ConnectionClosed, ProtocolError
from scrnshr.netutil import DEFAULT_PORT, enable_tcp_keepalive, peer_block_reason
from scrnshr.protocol import (
    DEFERRED_TYPES,
    PROTOCOL_VERSION,
    read_one,
    send_msg,
)

BUTTONS = frozenset({"left", "right", "middle"})
_COORD_LIMIT = 5000


class HostServer:
    """监听一个 TCP 端口。同一时间只接受一个已通过密码校验的控制端。

    injector 需要提供 move(dx, dy)、button(name, down)、scroll(dx, dy)、
    key(spec, down) 和 release_all()。断开时一定会调用 release_all，避免按键卡住。
    """

    def __init__(
        self,
        injector,
        password: str,
        port: int = DEFAULT_PORT,
        bind_host: str = "0.0.0.0",
    ) -> None:
        if not password:
            raise ValueError("密码不能为空")
        self.injector = injector
        self.password = password
        self.port = port
        self.bind_host = bind_host
        self._server: socket.socket | None = None
        self._client: socket.socket | None = None
        self._worker: threading.Thread | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._on_status = None

    def set_status_callback(self, callback) -> None:
        self._on_status = callback

    def set_password(self, password: str) -> None:
        if not password:
            raise ValueError("密码不能为空")
        with self._lock:
            self.password = password

    def start(self) -> None:
        if self._running:
            return
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform == "win32":
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                server.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        else:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.bind_host, self.port))
        except OSError as exc:
            server.close()
            raise BindError(f"端口 {self.port} 无法监听，可能已经被占用。") from exc
        server.listen(5)
        server.settimeout(0.3)
        self.port = server.getsockname()[1]
        self._server = server
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="scrnshr-accept", daemon=True)
        self._thread.start()
        self._emit("waiting")

    def stop(self) -> None:
        self._running = False
        with self._lock:
            client = self._client
        if client is not None:
            try:
                send_msg(client, {"t": "bye"})
            except OSError:
                pass
            _close_socket(client)
        if self._server is not None:
            _close_socket(self._server)
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        self._safe_release()

    def _accept_loop(self) -> None:
        while self._running:
            server = self._server
            if server is None:
                break
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            peer_ip = addr[0]
            with self._lock:
                busy = self._client is not None
            reason = peer_block_reason(peer_ip, busy)
            if reason:
                self._reject(conn, reason)
                self._emit("denied", reason, peer_ip)
                continue
            enable_tcp_keepalive(conn)
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            with self._lock:
                if self._client is not None:
                    self._reject(conn, "busy")
                    self._emit("denied", "busy", peer_ip)
                    continue
                self._client = conn
            worker = threading.Thread(
                target=self._serve,
                args=(conn, peer_ip),
                name="scrnshr-session",
                daemon=True,
            )
            self._worker = worker
            worker.start()

    def _serve(self, conn: socket.socket, peer_ip: str) -> None:
        try:
            self._session(conn, peer_ip)
        except (ConnectionClosed, ProtocolError, AuthError, TimeoutError, OSError):
            pass
        finally:
            self._safe_release()
            _close_socket(conn)
            with self._lock:
                if self._client is conn:
                    self._client = None
            self._emit("waiting")

    def _session(self, conn: socket.socket, peer_ip: str) -> None:
        nonce = new_nonce()
        send_msg(conn, {"t": "hello", "v": PROTOCOL_VERSION, "nonce": nonce})
        conn.settimeout(5)
        buffer = bytearray()
        message = read_one(conn, buffer)
        if message.get("t") != "auth" or message.get("v") != PROTOCOL_VERSION:
            send_msg(conn, {"t": "deny", "reason": "version"})
            self._emit("denied", "version", peer_ip)
            raise ProtocolError("version")
        with self._lock:
            password = self.password
        if not verify(password, nonce, str(message.get("proof", ""))):
            send_msg(conn, {"t": "deny", "reason": "auth"})
            self._emit("denied", "auth", peer_ip)
            raise AuthError("auth")
        send_msg(conn, {"t": "ok", "v": PROTOCOL_VERSION})
        conn.settimeout(None)
        self._emit("connected", peer_ip)
        while self._running:
            incoming = read_one(conn, buffer)
            self._dispatch(incoming)

    def _dispatch(self, message: dict) -> None:
        kind = message.get("t")
        if kind == "bye":
            raise ConnectionClosed()
        if kind == "release_all":
            self._safe_release()
            return
        if kind in DEFERRED_TYPES:
            return
        if kind == "move":
            self.injector.move(_coord(message.get("dx")), _coord(message.get("dy")))
            return
        if kind == "button":
            name = message.get("b")
            if name not in BUTTONS:
                raise ProtocolError("未知鼠标按键")
            self.injector.button(name, _as_bool(message.get("down")))
            return
        if kind == "scroll":
            self.injector.scroll(_coord(message.get("dx")), _coord(message.get("dy")))
            return
        if kind == "key":
            self.injector.key(_key_spec(message), _as_bool(message.get("down")))
            return

    def _reject(self, conn: socket.socket, reason: str) -> None:
        try:
            conn.settimeout(2)
            send_msg(conn, {"t": "deny", "reason": reason})
        except OSError:
            pass
        _close_socket(conn)

    def _emit(self, *payload) -> None:
        callback = self._on_status
        if callback is None:
            return
        try:
            callback(*payload)
        except Exception:
            pass

    def _safe_release(self) -> None:
        try:
            self.injector.release_all()
        except Exception:
            pass


def _coord(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("坐标不正确")
    if value > _COORD_LIMIT:
        return _COORD_LIMIT
    if value < -_COORD_LIMIT:
        return -_COORD_LIMIT
    return value


def _as_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ProtocolError("按下状态不正确")
    return value


def _key_spec(message: dict) -> dict:
    kind = message.get("kind")
    value = message.get("v")
    if kind == "char":
        if not isinstance(value, str) or len(value) != 1 or ord(value) < 32:
            raise ProtocolError("字符按键不正确")
        return {"kind": "char", "v": value}
    if kind == "key":
        if not isinstance(value, str) or not value.replace("_", "").isalnum() or len(value) > 32:
            raise ProtocolError("特殊按键不正确")
        return {"kind": "key", "v": value}
    if kind == "vk":
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 254:
            raise ProtocolError("虚拟键不正确")
        return {"kind": "vk", "v": value}
    raise ProtocolError("按键类型不正确")


def _close_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
