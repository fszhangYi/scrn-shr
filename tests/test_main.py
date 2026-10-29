import pathfix  # noqa: F401

import unittest

from scrnshr.__main__ import main


class MainTests(unittest.TestCase):
    def test_help(self):
        self.assertEqual(main(["--help"]), 0)

    def test_unknown_command(self):
        self.assertEqual(main(["nope"]), 2)


if __name__ == "__main__":
    unittest.main()
