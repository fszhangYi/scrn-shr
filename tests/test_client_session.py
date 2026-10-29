import pathfix  # noqa: F401

import time
import unittest

from recording import RecordingInjector

from scrnshr.client_session import ClientSession
from scrnshr.errors import AuthError, BusyError, LanError
from scrnshr.host_server import HostServer


def wait_for(predicate, timeout=3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class ClientSessionTests(unittest.TestCase):
    def setUp(self):
        self.injector = RecordingInjector()
        self.server = HostServer(self.injector, "123456", port=0, bind_host="127.0.0.1")
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_public_address_is_refused_before_connecting(self):
        session = ClientSession()
        with self.assertRaises(LanError):
            session.connect("8.8.8.8", self.server.port, "123456")
        self.assertEqual(self.injector.events, [])

    def test_events_arrive_and_close_releases_keys(self):
        session = ClientSession()
        session.connect("127.0.0.1", self.server.port, "123456")
        session.send({"t": "move", "dx": 4, "dy": 5})
        session.send({"t": "button", "b": "right", "down": True})
        session.send({"t": "button", "b": "right", "down": False})
        session.send({"t": "key", "kind": "vk", "v": 66, "down": True})
        self.assertTrue(wait_for(lambda: ("key", "vk", 66, True) in self.injector.events))
        session.close()
        self.assertTrue(wait_for(lambda: ("release_all",) in self.injector.events))
        self.assertIn(("move", 4, 5), self.injector.events)
        self.assertIn(("button", "right", True), self.injector.events)

    def test_wrong_password(self):
        session = ClientSession()
        with self.assertRaises(AuthError):
            session.connect("127.0.0.1", self.server.port, "000000")
        self.assertNotIn(("move", 1, 1), self.injector.events)

    def test_second_session_is_busy(self):
        first = ClientSession()
        first.connect("127.0.0.1", self.server.port, "123456")
        self.addCleanup(first.close)
        second = ClientSession()
        with self.assertRaises(BusyError):
            second.connect("127.0.0.1", self.server.port, "123456")


if __name__ == "__main__":
    unittest.main()
