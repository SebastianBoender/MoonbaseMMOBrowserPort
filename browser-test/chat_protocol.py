"""Bridge Moonbase's byte-valued chat cipher to the Director 12 UTF-8 wire.

Only MC.content[2] is translated. The original Lingo encryption, room routing,
sender identity and timestamp checks remain in the game. No plaintext is logged.
"""
import struct

MAX_PACKET = 1024 * 1024


def _string_end(packet, offset):
    length = struct.unpack_from('!I', packet, offset)[0]
    start = offset + 4
    end = start + length
    padded = end + length % 2
    if padded > len(packet):
        raise ValueError('Truncated MUS string')
    return start, end, padded


def _cipher_bytes(value):
    return bool(value) and len(value) % 2 == 0 and all(b & 15 == 15 for b in value)


def translate_chat_packet(packet, direction):
    """Return a MUS payload, preserving every field except cipher encoding."""
    if direction not in ('client', 'server'):
        raise ValueError('Unknown chat direction')
    try:
        start, end, offset = _string_end(packet, 8)
        if packet[start:end] != b'MC':
            return packet
        _, _, offset = _string_end(packet, offset)  # sender
        recipients = struct.unpack_from('!I', packet, offset)[0]
        offset += 4
        # A recipient needs at least a four-byte string length.
        if recipients > (len(packet) - offset) // 4:
            return packet
        for _ in range(recipients):
            _, _, offset = _string_end(packet, offset)
        tag, count = struct.unpack_from('!HI', packet, offset)
        if (tag, count) != (7, 2):  # [userID, encrypted string]
            return packet
        offset += 6
        code_tag = struct.unpack_from('!H', packet, offset)[0]
        offset += 2
        if code_tag == 3:
            _, _, offset = _string_end(packet, offset)
        elif code_tag == 1:
            offset += 4
        else:
            return packet
        if struct.unpack_from('!H', packet, offset)[0] != 3:
            return packet
        field = offset + 2
        start, end, padded = _string_end(packet, field)
        if padded != len(packet):
            return packet
        cipher = packet[start:end]
        if direction == 'client':
            if not _cipher_bytes(cipher):
                return packet
            replacement = cipher.decode('latin1').encode('utf-8')
        else:
            # Accept both Unicode projectors and older byte-based peers.
            # Strict decoding avoids replacing invalid bytes with U+FFFD.
            replacement = cipher.decode('utf-8').encode('latin1')
            if not _cipher_bytes(replacement):
                return packet
        if replacement == cipher:
            return packet
        return (packet[:field] + struct.pack('!I', len(replacement)) +
                replacement + b'\0' * (len(replacement) % 2))
    except (ValueError, UnicodeError, struct.error):
        # Unknown MC layouts and malformed values retain their original bytes.
        return packet


class ChatStream:
    """Reassemble MUS frames across arbitrary TCP/WebSocket chunk boundaries."""
    def __init__(self, direction):
        if direction not in ('client', 'server'):
            raise ValueError('Unknown chat direction')
        self.direction = direction
        self.buffer = bytearray()
        self.passthrough = False

    def feed(self, chunk):
        if self.passthrough:
            return chunk
        self.buffer.extend(chunk)
        output = bytearray()
        while len(self.buffer) >= 6:
            size = struct.unpack_from('!I', self.buffer, 2)[0]
            if self.buffer[:2] != b'\x72\0' or size > MAX_PACKET:
                # Preserve the transport's behavior for unrecognized streams.
                self.passthrough = True
                output.extend(self.buffer)
                self.buffer.clear()
                break
            if len(self.buffer) < size + 6:
                break
            packet = translate_chat_packet(bytes(self.buffer[6:size + 6]), self.direction)
            del self.buffer[:size + 6]
            output.extend(b'\x72\0' + struct.pack('!I', len(packet)) + packet)
        return bytes(output)
