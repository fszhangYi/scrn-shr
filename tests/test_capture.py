import pathfix  # noqa: F401

import unittest

from pynput.keyboard import Key, KeyCode

from scrnshr.capture import spec_from_pynput


class SpecTests(unittest.TestCase):
    def test_modifiers_keep_their_names(self):
        self.assertEqual(spec_from_pynput(Key.ctrl_l), {"kind": "key", "v": "ctrl_l"})
        self.assertEqual(spec_from_pynput(Key.esc), {"kind": "key", "v": "esc"})

    def test_virtual_key_is_preferred(self):
        self.assertEqual(spec_from_pynput(KeyCode.from_vk(65)), {"kind": "vk", "v": 65})

    def test_character_is_used_when_there_is_no_virtual_key(self):
        self.assertEqual(spec_from_pynput(KeyCode.from_char("a")), {"kind": "char", "v": "a"})


if __name__ == "__main__":
    unittest.main()
