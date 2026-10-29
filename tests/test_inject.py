import pathfix  # noqa: F401

import unittest

from scrnshr.inject import PynputInjector, parse_key


class FakeMouse:
    def __init__(self) -> None:
        self.moves = []
        self.presses = []
        self.releases = []
        self.scrolls = []

    def move(self, dx, dy) -> None:
        self.moves.append((dx, dy))

    def press(self, button) -> None:
        self.presses.append(button)

    def release(self, button) -> None:
        self.releases.append(button)

    def scroll(self, dx, dy) -> None:
        self.scrolls.append((dx, dy))


class FakeKeyboard:
    def __init__(self) -> None:
        self.presses = []
        self.releases = []

    def press(self, key) -> None:
        self.presses.append(key)

    def release(self, key) -> None:
        self.releases.append(key)


class InjectTests(unittest.TestCase):
    def test_parse_known_keys(self):
        self.assertIsNotNone(parse_key({"kind": "key", "v": "enter"}))
        self.assertIsNotNone(parse_key({"kind": "char", "v": "a"}))
        self.assertIsNotNone(parse_key({"kind": "vk", "v": 65}))
        self.assertIsNone(parse_key({"kind": "key", "v": "not_a_real_key"}))

    def test_release_all_lets_go_of_held_input(self):
        mouse = FakeMouse()
        keyboard = FakeKeyboard()
        injector = PynputInjector(mouse=mouse, keyboard=keyboard)
        injector.move(2, -3)
        injector.button("left", True)
        injector.key({"kind": "key", "v": "shift"}, True)
        injector.key({"kind": "vk", "v": 65}, True)
        injector.scroll(0, 1)
        injector.release_all()
        self.assertEqual(mouse.moves, [(2, -3)])
        self.assertEqual(len(mouse.presses), 1)
        self.assertEqual(len(mouse.releases), 1)
        self.assertEqual(keyboard.releases[-2:], list(reversed(keyboard.presses)))
        injector.release_all()
        self.assertEqual(len(keyboard.releases), 2)

    def test_unknown_key_is_ignored(self):
        keyboard = FakeKeyboard()
        injector = PynputInjector(mouse=FakeMouse(), keyboard=keyboard)
        injector.key({"kind": "key", "v": "not_a_real_key"}, True)
        self.assertEqual(keyboard.presses, [])


if __name__ == "__main__":
    unittest.main()
