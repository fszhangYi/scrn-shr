import pathfix  # noqa: F401

import socket
import threading
import time
import unittest

from recording import RecordingInjector

from scrnshr.auth import proof
from scrnshr.errors import ProtocolError
from scrnshr.host_server import HostServer
from scrnshr.protocol import read_one, send_msg


def wait_for(predicate, timeout=3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class HostServerTests(unittest.TestCase):
    def setUp(self):
        self.injector = RecordingInjector()
        self.password = "123456"
        self.server = HostServer(self.injector, self.password, port=0, bind_host="127.0.0.1")
        self.server.start()
        self.addCleanup(self.server.stop)

    def _open(self, password=None):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        sock.settimeout(2)
        self.addCleanup(lambda: _quiet_close(sock))
        buffer = bytearray()
        hello = read_one(sock, buffer)
        pin = self.password if password is None else password
        send_msg(sock, {"t": "auth", "v": 1, "proof": proof(pin, hello["nonce"])})
        reply = read_one(sock, buffer)
        return sock, buffer, hello, reply

    def test_auth_and_input_events(self):
        sock, buffer, hello, reply = self._open()
        self.assertEqual(hello["t"], "hello")
        self.assertEqual(reply["t"], "ok")
        send_msg(sock, {"t": "move", "dx": 3, "dy": -4})
        send_msg(sock, {"t": "button", "b": "left", "down": True})
        send_msg(sock, {"t": "button", "b": "left", "down": False})
        send_msg(sock, {"t": "scroll", "dx": 0, "dy": -1})
        send_msg(sock, {"t": "key", "kind": "char", "v": "a", "down": True})
        send_msg(sock, {"t": "key", "kind": "vk", "v": 65, "down": False})
        self.assertTrue(
            wait_for(
                lambda: ("key", "vk", 65, False) in self.injector.events
            ),
            self.injector.events,
        )
        self.assertIn(("move", 3, -4), self.injector.events)
        self.assertIn(("button", "left", True), self.injector.events)
        self.assertIn(("scroll", 0, -1), self.injector.events)

    def test_wrong_password_injects_nothing(self):
        _sock, _buffer, _hello, reply = self._open("000000")
        self.assertEqual(reply, {"t": "deny", "reason": "auth"})
        time.sleep(0.2)
        self.assertEqual(self.injector.events, [("release_all",)])

    def test_second_client_is_busy(self):
        first, _buffer, _hello, reply = self._open()
        self.assertEqual(reply["t"], "ok")
        self.assertTrue(wait_for(lambda: self.server._client is not None))
        second = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        second.settimeout(2)
        self.addCleanup(lambda: _quiet_close(second))
        denied = read_one(second, bytearray())
        self.assertEqual(denied, {"t": "deny", "reason": "busy"})
        _quiet_close(first)

    def test_deferred_messages_do_not_reach_the_injector(self):
        sock, _buffer, _hello, reply = self._open()
        self.assertEqual(reply["t"], "ok")
        before = len(self.injector.events)
        for kind in ("screen", "file", "clipboard"):
            send_msg(sock, {"t": kind, "payload": "ignored"})
        send_msg(sock, {"t": "move", "dx": 1, "dy": 1})
        self.assertTrue(wait_for(lambda: ("move", 1, 1) in self.injector.events))
        kinds = [event[0] for event in self.injector.events[before:]]
        self.assertNotIn("screen", kinds)
        self.assertNotIn("file", kinds)
        self.assertNotIn("clipboard", kinds)

    def test_abrupt_disconnect_releases_keys(self):
        sock, _buffer, _hello, reply = self._open()
        self.assertEqual(reply["t"], "ok")
        send_msg(sock, {"t": "key", "kind": "key", "v": "shift", "down": True})
        self.assertTrue(wait_for(lambda: ("key", "key", "shift", True) in self.injector.events))
        _quiet_close(sock)
        self.assertTrue(wait_for(lambda: self.injector.events[-1] == ("release_all",)))

    def test_malformed_key_drops_the_session(self):
        sock, _buffer, _hello, reply = self._open()
        self.assertEqual(reply["t"], "ok")
        send_msg(sock, {"t": "key", "kind": "char", "v": "ab", "down": True})
        self.assertTrue(wait_for(lambda: self.injector.events[-1] == ("release_all",)))

    def test_move_before_auth_does_not_inject(self):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=2)
        sock.settimeout(2)
        self.addCleanup(lambda: _quiet_close(sock))
        buffer = bytearray()
        hello = read_one(sock, buffer)
        self.assertEqual(hello["t"], "hello")
        send_msg(sock, {"t": "move", "dx": 9, "dy": 9})
        reply = read_one(sock, buffer)
        self.assertEqual(reply["t"], "deny")
        time.sleep(0.2)
        self.assertNotIn(("move", 9, 9), self.injector.events)

    def test_bind_error_on_used_port(self):
        other = HostServer(RecordingInjector(), "123456", port=self.server.port, bind_host="127.0.0.1")
        with self.assertRaises(Exception):
            other.start()


class DispatchGuardTests(unittest.TestCase):
    def test_coordinate_helper_rejects_bool(self):
        from scrnshr.host_server import _coord

        with self.assertRaises(ProtocolError):
            _coord(True)


class StopReleasesTests(unittest.TestCase):
    def test_stop_unblocks_a_connected_client(self):
        injector = RecordingInjector()
        server = HostServer(injector, "123456", port=0, bind_host="127.0.0.1")
        server.start()
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=2)
        sock.settimeout(2)
        buffer = bytearray()
        hello = read_one(sock, buffer)
        send_msg(sock, {"t": "auth", "v": 1, "proof": proof("123456", hello["nonce"])})
        self.assertEqual(read_one(sock, buffer)["t"], "ok")
        done = threading.Event()

        def wait_peer():
            try:
                read_one(sock, buffer)
            except Exception:
                pass
            done.set()

        threading.Thread(target=wait_peer, daemon=True).start()
        server.stop()
        self.assertTrue(done.wait(3))
        self.assertIn(("release_all",), injector.events)
        _quiet_close(sock)


def _quiet_close(sock) -> None:
    try:
        sock.close()
    except OSError:
        pass


if __name__ == "__main__":
    unittest.main()
