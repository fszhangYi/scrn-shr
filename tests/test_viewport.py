import pathfix  # noqa: F401

import os
import unittest

from PIL import Image

from scrnshr.errors import ProtocolError
from scrnshr.protocol import MAX_MESSAGE, pack
from scrnshr.viewport import decode_screen, encode_screen, map_canvas_filled, map_canvas_to_screen


class ViewportTests(unittest.TestCase):
    def test_round_trip_and_center_click(self):
        image = Image.new("RGB", (100, 50), (20, 40, 60))
        message = encode_screen(image, origin_x=-100, origin_y=0, screen_w=200, screen_h=100, seq=3)
        restored, geometry = decode_screen(message)
        self.assertEqual(restored.size, (100, 50))
        self.assertEqual(geometry.origin_x, -100)
        point = map_canvas_to_screen(100, 50, 200, 100, geometry)
        self.assertEqual(point, (0, 50))

    def test_click_outside_the_picture_is_ignored(self):
        image = Image.new("RGB", (100, 50), "white")
        _message, geometry = decode_screen(encode_screen(image, 0, 0, 100, 50, 1))
        self.assertIsNone(map_canvas_to_screen(0, 0, 100, 100, geometry))

    def test_filled_canvas_reaches_both_edges(self):
        image = Image.new("RGB", (100, 50), "white")
        _message, geometry = decode_screen(encode_screen(image, 0, 0, 200, 100, 1))
        left = map_canvas_filled(0, 25, 300, 80, geometry)
        right = map_canvas_filled(299, 25, 300, 80, geometry)
        self.assertEqual(left[0], 0)
        self.assertGreater(right[0], 190)
        self.assertLessEqual(right[0], 200)

    def test_desktop_resolution_is_kept(self):
        image = Image.new("RGB", (1920, 1080), (30, 30, 30))
        _image, geometry = decode_screen(encode_screen(image, 0, 0, 1920, 1080, 1))
        self.assertEqual((geometry.image_w, geometry.image_h), (1920, 1080))
        self.assertEqual(geometry.screen_w, 1920)

    def test_large_frame_is_shrunk(self):
        image = Image.new("RGB", (4000, 2000), "black")
        _image, geometry = decode_screen(encode_screen(image, 0, 0, 4000, 2000, 1))
        self.assertLess(geometry.image_w, 4000)
        self.assertLessEqual(max(geometry.image_w, geometry.image_h), 2560)
        self.assertEqual(geometry.screen_w, 4000)

    def test_noisy_frame_stays_inside_one_message(self):
        image = Image.frombytes("RGB", (1600, 900), os.urandom(1600 * 900 * 3))
        message = encode_screen(image, 0, 0, 1600, 900, 1)
        self.assertLessEqual(len(pack(message)), 4 + MAX_MESSAGE)

    def test_rejects_a_non_jpeg_payload(self):
        with self.assertRaises(ProtocolError):
            decode_screen({"t": "screen", "jpg": "aaaa", "ox": 0, "oy": 0, "sw": 1, "sh": 1, "w": 1, "h": 1})


if __name__ == "__main__":
    unittest.main()
