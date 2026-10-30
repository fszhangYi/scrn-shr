import pathfix  # noqa: F401

import unittest

from scrnshr.errors import ProtocolError
from scrnshr.protocol import pack, pop_message


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        message = {"t": "move", "dx": 3, "dy": -4}
        buffer = bytearray(pack(message))
        self.assertEqual(pop_message(buffer), message)
        self.assertEqual(buffer, bytearray())

    def test_partial_header_waits(self):
        packed = pack({"t": "ok", "v": 1})
        buffer = bytearray(packed[:2])
        self.assertIsNone(pop_message(buffer))
        buffer.extend(packed[2:])
        self.assertEqual(pop_message(buffer)["t"], "ok")

    def test_two_messages_in_one_buffer(self):
        buffer = bytearray(pack({"t": "move", "dx": 1, "dy": 0}) + pack({"t": "bye"}))
        self.assertEqual(pop_message(buffer)["t"], "move")
        self.assertEqual(pop_message(buffer)["t"], "bye")
        self.assertIsNone(pop_message(buffer))

    def test_rejects_huge_declared_length(self):
        buffer = bytearray(b"\xff\xff\xff\xff")
        with self.assertRaises(ProtocolError):
            pop_message(buffer)

    def test_rejects_non_object(self):
        import json
        import struct

        payload = json.dumps([1, 2]).encode()
        buffer = bytearray(struct.pack(">I", len(payload)) + payload)
        with self.assertRaises(ProtocolError):
            pop_message(buffer)

    def test_screen_payload_round_trip(self):
        message = {"t": "screen", "jpg": "a" * (200 * 1024)}
        restored = pop_message(bytearray(pack(message)))
        self.assertEqual(restored["t"], "screen")
        self.assertEqual(len(restored["jpg"]), 200 * 1024)


if __name__ == "__main__":
    unittest.main()
