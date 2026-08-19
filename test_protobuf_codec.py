import base64
import unittest

from protobuf_codec import decode_psk, expand_key, packet_nonce
from protobuf_sender import channel_hash


class CryptoHelpersTests(unittest.TestCase):

    def test_channel_hashes(self):
        self.assertEqual(channel_hash("LZMesh", "uLT6S8kQlQHjA7yEtBkzIj3zm6K6lE55mulplDZyF/0="), 0x7F)
        self.assertEqual(channel_hash("LongFast", "AQ=="), 0x08)
        self.assertEqual(channel_hash("LZRF", "dTEweE82YjhWc1pRS1dzY1FESEk4dnlBcVM2SUxmV3c="), 0x3A)
    def test_lzmesh_key(self):
        key = decode_psk("uLT6S8kQlQHjA7yEtBkzIj3zm6K6lE55mulplDZyF/0=")
        self.assertEqual(len(key), 32)

    def test_nonce_layout(self):
        nonce = packet_nonce(0x11223344, 0xaabbccdd)
        self.assertEqual(nonce.hex(), "4433221100000000ddccbbaa00000000")

    def test_short_key(self):
        self.assertEqual(len(expand_key(bytes([1]))), 16)

    def test_lzrf_key(self):
        self.assertEqual(len(decode_psk("dTEweE82YjhWc1pRS1dzY1FESEk4dnlBcVM2SUxmV3c=")), 32)


if __name__ == "__main__": unittest.main()
