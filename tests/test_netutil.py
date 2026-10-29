import pathfix  # noqa: F401

import unittest

from scrnshr.netutil import (
    display_addresses,
    is_lan_ip,
    is_same_machine,
    parse_port,
    peer_block_reason,
    prepare_target,
)


class NetutilTests(unittest.TestCase):
    def test_private_and_loopback_are_allowed(self):
        for ip in ("10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.0.10", "127.0.0.1", "169.254.1.8"):
            self.assertTrue(is_lan_ip(ip), ip)

    def test_public_and_special_addresses_are_refused(self):
        for ip in ("8.8.8.8", "1.1.1.1", "172.32.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "desktop", ""):
            self.assertFalse(is_lan_ip(ip), ip)

    def test_strips_whitespace(self):
        self.assertTrue(is_lan_ip("  192.168.1.5  "))

    def test_peer_policy(self):
        self.assertIsNone(peer_block_reason("192.168.1.5", busy=False))
        self.assertEqual(peer_block_reason("192.168.1.5", busy=True), "busy")
        self.assertEqual(peer_block_reason("8.8.8.8", busy=False), "lan")

    def test_display_addresses_skip_loopback_and_public(self):
        shown = display_addresses(["127.0.0.1", "192.168.1.5", "8.8.8.8", "192.168.1.5", "10.0.0.8"])
        self.assertEqual(shown, ["192.168.1.5", "10.0.0.8"])

    def test_prepare_target_refuses_self_and_public(self):
        local = ["192.168.1.5"]
        self.assertEqual(prepare_target("10.0.0.9", local), "10.0.0.9")
        with self.assertRaises(ValueError):
            prepare_target("8.8.8.8", local)
        with self.assertRaises(ValueError):
            prepare_target("192.168.1.5", local)
        with self.assertRaises(ValueError):
            prepare_target("127.0.0.1", local)

    def test_same_machine_detects_loopback_without_a_local_list(self):
        self.assertTrue(is_same_machine("127.0.0.1", []))

    def test_parse_port(self):
        self.assertEqual(parse_port("47621"), 47621)
        with self.assertRaises(ValueError):
            parse_port("0")
        with self.assertRaises(ValueError):
            parse_port("abc")


if __name__ == "__main__":
    unittest.main()
