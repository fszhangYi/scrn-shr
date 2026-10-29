import pathfix  # noqa: F401

import unittest

from scrnshr.inputlogic import ForwardPolicy, PointerLockMath


class ForwardPolicyTests(unittest.TestCase):
    def test_ctrl_alt_q_disconnects_without_forwarding_q(self):
        policy = ForwardPolicy()
        self.assertEqual(policy.decide({"kind": "key", "v": "ctrl_l"}, True), "forward")
        self.assertEqual(policy.decide({"kind": "vk", "v": 0xA4}, True), "forward")
        self.assertEqual(policy.decide({"kind": "vk", "v": 0x51}, True), "disconnect")

    def test_escape_unlocks(self):
        policy = ForwardPolicy()
        self.assertEqual(policy.decide({"kind": "key", "v": "esc"}, True), "unlock")
        self.assertEqual(policy.decide({"kind": "vk", "v": 0x1B}, True), "unlock")

    def test_plain_q_is_forwarded(self):
        policy = ForwardPolicy()
        self.assertEqual(policy.decide({"kind": "char", "v": "q"}, True), "forward")
        self.assertEqual(policy.decide({"kind": "vk", "v": 65}, True), "forward")

    def test_releasing_modifiers_clears_the_hotkey(self):
        policy = ForwardPolicy()
        policy.decide({"kind": "key", "v": "ctrl_l"}, True)
        policy.decide({"kind": "key", "v": "alt_l"}, True)
        policy.decide({"kind": "key", "v": "ctrl_l"}, False)
        policy.decide({"kind": "key", "v": "alt_l"}, False)
        self.assertEqual(policy.decide({"kind": "char", "v": "Q"}, True), "forward")


class PointerLockTests(unittest.TestCase):
    def test_jump_is_ignored_until_the_cursor_returns_to_center(self):
        pointer = PointerLockMath()
        self.assertIsNone(pointer.on_move(10, 10, 100, 100))
        self.assertFalse(pointer.armed)
        self.assertIsNone(pointer.on_move(50, 51, 100, 100))
        self.assertTrue(pointer.armed)
        self.assertEqual(pointer.on_move(58, 47, 100, 100), (8, -3))
        self.assertIsNone(pointer.on_move(50, 50, 100, 100))

    def test_manual_arm_drops_the_next_event(self):
        pointer = PointerLockMath()
        pointer.arm()
        self.assertIsNone(pointer.on_move(80, 80, 100, 100))
        self.assertEqual(pointer.on_move(60, 55, 100, 100), (10, 5))

    def test_second_arm_does_not_drop_another_event(self):
        pointer = PointerLockMath()
        pointer.on_move(50, 50, 100, 100)
        pointer.arm()
        self.assertEqual(pointer.on_move(54, 50, 100, 100), (4, 0))


if __name__ == "__main__":
    unittest.main()
