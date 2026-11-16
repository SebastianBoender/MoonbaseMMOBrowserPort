"""Native Director 12 wire fixture and stream-boundary regressions."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_protocol import ChatStream, translate_chat_packet


def mus_string(value):
    return struct.pack('!I', len(value)) + value + b'\0' * (len(value) % 2)


def packet(cipher, subject=b'MC', code_tag=3):
    code = mus_string(b'123456') if code_tag == 3 else struct.pack('!i', 123456)
    return (struct.pack('!iI', 0, 0) + mus_string(subject) + mus_string(b'123456') +
            struct.pack('!I', 1) + mus_string(b'127.0.0.1') +
            struct.pack('!HIH', 7, 2, code_tag) + code + struct.pack('!H', 3) + mus_string(cipher))


def frame(payload):
    return b'\x72\0' + struct.pack('!I', len(payload)) + payload


# Captured from the supplied Director 12 projector under Wine, using a
# disposable movie adapter and loopback-only MUS fixture. Plaintext was
# "MoonBase0429", encrypted by the actual native EncryptString with key 123456.
NATIVE_PACKET = bytes.fromhex(
    '0000000000000000000000024d430000000631323334353600000001000000093132372e302e302e3100'
    '00070000000200030000000631323334353600030000001d'
    'c38f7fc39f5fc38f5fc2af5f7f7f7f5f2f4f7f5f3f0f0f0f7f0fc3bf0f00')
RAW_CIPHER = bytes([207, 127, 223, 95, 207, 95, 175, 95, 127, 127, 127, 95,
                    47, 79, 127, 95, 63, 15, 15, 15, 127, 15, 255, 15])


class ChatProtocolTests(unittest.TestCase):
    def test_browser_output_matches_captured_native_packet(self):
        self.assertEqual(translate_chat_packet(packet(RAW_CIPHER), 'client'), NATIVE_PACKET)

    def test_native_packet_decodes_to_original_browser_cipher(self):
        self.assertEqual(translate_chat_packet(NATIVE_PACKET, 'server'), packet(RAW_CIPHER))

    def test_every_cipher_nibble_and_integer_sender(self):
        raw = bytes(range(15, 256, 16))
        for tag in (1, 3):
            with self.subTest(tag=tag):
                self.assertEqual(translate_chat_packet(packet(raw, code_tag=tag), 'client'),
                                 packet(raw.decode('latin1').encode('utf8'), code_tag=tag))

    def test_existing_utf8_client_and_old_byte_peer_are_preserved(self):
        self.assertEqual(translate_chat_packet(NATIVE_PACKET, 'client'), NATIVE_PACKET)
        self.assertEqual(translate_chat_packet(packet(RAW_CIPHER), 'server'), packet(RAW_CIPHER))

    def test_other_subjects_and_non_cipher_chat_are_unchanged(self):
        for payload in (packet(RAW_CIPHER, b'MP'), packet(b'ordinary text'),
                        packet(b'\xff'), packet(b'\xef\xbf\xbd'), NATIVE_PACKET + b'extra'):
            for direction in ('client', 'server'):
                self.assertEqual(translate_chat_packet(payload, direction), payload)

    def test_truncated_fields_are_unchanged(self):
        for i in range(len(NATIVE_PACKET)):
            payload = NATIVE_PACKET[:i]
            self.assertEqual(translate_chat_packet(payload, 'server'), payload)

    def test_tcp_and_websocket_boundaries_and_coalesced_frames(self):
        before = frame(packet(RAW_CIPHER)) + frame(packet(b'untouched', b'MP'))
        after = frame(NATIVE_PACKET) + frame(packet(b'untouched', b'MP'))
        for boundary in range(len(before) + 1):
            stream = ChatStream('client')
            self.assertEqual(stream.feed(before[:boundary]) + stream.feed(before[boundary:]), after)
        stream = ChatStream('server')
        self.assertEqual(b''.join(stream.feed(bytes([b])) for b in after), before)

    def test_non_mus_and_oversized_headers_remain_passthrough(self):
        for data in (bytes(range(256)), b'\x72\0' + struct.pack('!I', 2**31)):
            stream = ChatStream('client')
            self.assertEqual(stream.feed(data), data)
            self.assertEqual(stream.feed(b'later'), b'later')


if __name__ == '__main__':
    unittest.main()
