import base64, io, os, socket, struct, sys, threading
from functools import partial
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mus_bridge, serve
from test_chat_protocol import NATIVE_PACKET, RAW_CIPHER, frame, packet
import queue
observed_chat = queue.Queue()
listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
mus_bridge.REMOTE=listener.getsockname()
def echo():
 with listener.accept()[0] as c:
  # The real WebSocket bridge must produce the captured native wire packet.
  native = mus_bridge.read_exact(c.makefile('rb', buffering=0), len(frame(NATIVE_PACKET)))
  observed_chat.put(native)
  for offset in range(0, len(native), 3):
   c.sendall(native[offset:offset + 3])
  while b:=c.recv(65536): c.sendall(b)
threading.Thread(target=echo,daemon=True).start()
server=ThreadingHTTPServer(('127.0.0.1',0),partial(serve.Handler,directory=str(serve.PUBLIC)))
production = '--production' in sys.argv
if production:
 server.production = True
 server.allowed_origins = ('https://moonbasemmo.com',)
origin = 'https://moonbasemmo.com' if production else f'http://127.0.0.1:{server.server_port}'
threading.Thread(target=server.serve_forever,daemon=True).start()
# Untrusted origins are rejected before opening an upstream TCP connection.
with socket.create_connection(server.server_address) as denied:
 denied.sendall(b'GET /mus HTTP/1.1\r\nHost: localhost\r\nOrigin: https://evil.example\r\n\r\n')
 assert b'403' in denied.recv(4096)
c=socket.create_connection(server.server_address); c.settimeout(3)
c.sendall((f'GET /mus HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\nOrigin: {origin}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\n\r\n').encode())
f=c.makefile('rb',buffering=0)
assert b'101' in f.readline()
while f.readline()!=b'\r\n':pass
def masked(op,b,final=True):
 mask=b'abcd'; n=len(b)
 return bytes([(128 if final else 0)|op])+ (bytes([128|n]) if n<126 else b'\xfe'+struct.pack('!H',n))+mask+bytes(x^mask[i%4] for i,x in enumerate(b))
def read():
 a,b=mus_bridge.read_exact(f,2); n=b&127
 if n==126:n=struct.unpack('!H',mus_bridge.read_exact(f,2))[0]
 if n==127:n=struct.unpack('!Q',mus_bridge.read_exact(f,8))[0]
 return a&15,mus_bridge.read_exact(f,n)
c.sendall(masked(9,b'ping')); assert read()==(10,b'ping')
browser_chat = frame(packet(RAW_CIPHER))
# A MUS packet can also span separate, complete WebSocket messages.
c.sendall(masked(2,browser_chat[:5])+masked(2,browser_chat[5:]))
chat_reply=b''
while len(chat_reply)<len(browser_chat):
 op,b=read(); assert op==2; chat_reply+=b
assert chat_reply==browser_chat
assert observed_chat.get(timeout=3)==frame(NATIVE_PACKET)
payload=bytes(range(256))*2
# Coalesced fragmented frames also exercise unbuffered socket reads.
c.sendall(masked(2,payload[:200],False)+masked(0,payload[200:]))
result=b''
while len(result)<len(payload):
 op,b=read(); assert op==2; result+=b
assert result==payload
c.sendall(masked(8,struct.pack('!H',1000))); assert read()[0]==8
c.close(); server.shutdown(); server.server_close(); listener.close()
print('PASS: native chat translation both ways, chunk boundaries, upgrade, fragmentation, binary relay, ping/pong, close')
