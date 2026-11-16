"""Local WebSocket transport for the game's fixed legacy TCP endpoint."""
import base64
import hashlib
import select
import socket
import struct
from chat_protocol import ChatStream

REMOTE = ('pigyak.com', 1626)
MAX_FRAME = 1024 * 1024


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def read_frame(stream):
    first, second = read_exact(stream, 2)
    opcode = first & 15
    if first & 0x70 or not second & 0x80:
        raise ValueError('Invalid or unmasked WebSocket frame')
    size = second & 127
    if size == 126:
        size = struct.unpack('!H', read_exact(stream, 2))[0]
    elif size == 127:
        size = struct.unpack('!Q', read_exact(stream, 8))[0]
    if size > MAX_FRAME or (opcode >= 8 and (size > 125 or not first & 128)):
        raise ValueError('Invalid WebSocket frame size')
    mask = read_exact(stream, 4)
    data = read_exact(stream, size)
    return bool(first & 128), opcode, bytes(b ^ mask[i % 4] for i, b in enumerate(data))


def send_frame(connection, data, opcode=2):
    size = len(data)
    header = bytes([128 | opcode])
    header += bytes([size]) if size < 126 else (b'\x7e' + struct.pack('!H', size) if size < 65536 else b'\x7f' + struct.pack('!Q', size))
    connection.sendall(header + data)


class MusTrace:
    """Log framing metadata only; never player names, passwords or message content."""
    def __init__(self, handler, direction):
        self.handler, self.direction, self.buffer = handler, direction, bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        while len(self.buffer) >= 6:
            if self.buffer[:2] != b'\x72\x00':
                self.buffer.clear()
                return
            size = struct.unpack_from('!I', self.buffer, 2)[0]
            if size > MAX_FRAME:
                self.buffer.clear()
                return
            if len(self.buffer) < size + 6:
                return
            frame = bytes(self.buffer[6:size + 6])
            del self.buffer[:size + 6]
            if len(frame) >= 12:
                error, _, length = struct.unpack_from('!iII', frame)
                if length <= 128 and 12 + length <= len(frame):
                    subject = frame[12:12 + length].decode('latin1')
                    self.handler.log_message('MUS %s frame: subject=%r error=%d size=%d',
                                             self.direction, subject, error, size)


def proxy(handler):
    # Fixed target and explicit browser origins; never an arbitrary TCP proxy.
    expected = f'http://127.0.0.1:{handler.server.server_port}'
    origin = handler.headers.get('Origin')
    allowed = getattr(handler.server, 'allowed_origins', None) or (expected, f'http://localhost:{handler.server.server_port}')
    if origin not in allowed:
        return handler.send_error(403, 'Same-origin browser required')
    key = handler.headers.get('Sec-WebSocket-Key', '')
    try:
        valid_key = len(base64.b64decode(key, validate=True)) == 16
    except ValueError:
        valid_key = False
    if (not valid_key or handler.headers.get('Upgrade', '').lower() != 'websocket'
            or 'upgrade' not in handler.headers.get('Connection', '').lower()
            or handler.headers.get('Sec-WebSocket-Version') != '13'):
        return handler.send_error(400, 'WebSocket upgrade required')
    try:
        upstream = socket.create_connection(REMOTE, timeout=5)
    except OSError as error:
        handler.log_error('Legacy server connection failed: %s', error)
        return handler.json_response(502, {'error': 'Legacy server unavailable', 'target': 'pigyak.com:1626'})
    handler.close_connection = True
    with upstream:
        handler.connection.settimeout(10)
        upstream.settimeout(10)
        handler.protocol_version = 'HTTP/1.1'
        handler.send_response(101)
        handler.send_header('Upgrade', 'websocket')
        handler.send_header('Connection', 'Upgrade')
        accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        handler.send_header('Sec-WebSocket-Accept', accept)
        handler.end_headers()
        handler.wfile.flush()
        handler.log_message('MUS bridge connected to %s:%s', *REMOTE)
        fragmented = None
        sent_bytes = received_bytes = 0
        incoming_trace = MusTrace(handler, "server")
        outgoing_trace = MusTrace(handler, "client")
        incoming_chat = ChatStream('server')
        outgoing_chat = ChatStream('client')
        trace = not getattr(handler.server, 'production', False)
        try:
            while True:
                ready, _, _ = select.select([handler.connection, upstream], [], [], 60)
                if not ready:
                    continue
                if upstream in ready:
                    chunk = upstream.recv(65536)
                    if not chunk:
                        handler.log_message('MUS upstream EOF; sent=%d received=%d', sent_bytes, received_bytes)
                        send_frame(handler.connection, struct.pack('!H', 1000), 8)
                        break
                    if trace:
                        incoming_trace.feed(chunk)
                    received_bytes += len(chunk)
                    if trace:
                        handler.log_message('MUS received %d bytes; header=%s', len(chunk), chunk[:6].hex())
                    translated = incoming_chat.feed(chunk)
                    if translated:
                        send_frame(handler.connection, translated)
                if handler.connection in ready:
                    final, opcode, data = read_frame(handler.rfile)
                    if opcode == 8:
                        send_frame(handler.connection, data, 8)
                        break
                    if opcode == 9:
                        send_frame(handler.connection, data, 10)
                    elif opcode == 10:
                        continue
                    elif opcode == 2 and fragmented is None:
                        if final:
                            data = outgoing_chat.feed(data)
                            if data:
                                upstream.sendall(data)
                            if trace:
                                outgoing_trace.feed(data)
                            sent_bytes += len(data)
                            if trace:
                                handler.log_message('MUS sent %d bytes; header=%s', len(data), data[:6].hex())
                        else:
                            fragmented = bytearray(data)
                    elif opcode == 0 and fragmented is not None:
                        fragmented.extend(data)
                        if len(fragmented) > MAX_FRAME:
                            raise ValueError('Message too large')
                        if final:
                            data = outgoing_chat.feed(fragmented)
                            if data:
                                upstream.sendall(data)
                            if trace:
                                outgoing_trace.feed(data)
                            sent_bytes += len(data)
                            if trace:
                                handler.log_message('MUS sent fragmented %d bytes', len(fragmented))
                            fragmented = None
                    else:
                        raise ValueError('Binary MUS messages required')
        except (OSError, EOFError, ValueError) as error:
            handler.log_message('MUS bridge closed: %s', error)
