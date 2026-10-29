import pathfix  # noqa: F401

import unittest

from scrnshr.auth import new_pin, proof, verify


class AuthTests(unittest.TestCase):
    def test_pin_is_six_digits(self):
        pin = new_pin()
        self.assertEqual(len(pin), 6)
        self.assertTrue(pin.isdigit())

    def test_proof_matches_only_the_same_password_and_nonce(self):
        nonce = "abc123"
        self.assertTrue(verify("654321", nonce, proof("654321", nonce)))
        self.assertFalse(verify("654321", nonce, proof("000000", nonce)))
        self.assertFalse(verify("654321", nonce, proof("654321", "other")))
        self.assertFalse(verify("654321", nonce, "nope"))


if __name__ == "__main__":
    unittest.main()
