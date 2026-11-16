"""Run an isolated copy of the bundled projector against a loopback MUS fixture."""
import argparse,hashlib,json,os,socket,struct,subprocess,sys,time
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path,help='Original package directory (read-only)')
parser.add_argument('--output',type=Path,required=True,help='Disposable Wine prefix and fixture output')
args=parser.parse_args()
# Require a network namespace with no external routes before running Wine.
if any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:]):
 raise SystemExit('Run inside an isolated network namespace, as documented in README.md.')
root=args.root.resolve();sys.path.insert(0,str(root/'browser-test'))
from compatibility import encode
out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
exe=bytearray((root/'MB_2010-10-08.exe').read_bytes());base=0x495504
assert hashlib.sha256(exe).hexdigest() == '6d7b81d5d1e76ca6ee7ca2f1fc4286ab19a62a344417f88d229f677280b43a3a'
movie=(root/'browser-test/public/game/moonbase.dir').read_bytes();mm=struct.unpack_from('<I',movie,24)[0];h,st,_,n=struct.unpack_from('<HHII',movie,mm+8)
res={i:struct.unpack_from('<4sII',movie,mm+8+h+i*st) for i in range(n)}
_,ln,off=res[1059];nd=movie[off+8:off+8+ln];cur,cnt=struct.unpack_from('>HH',nd,16);names=[]
for _ in range(cnt):l=nd[cur];names.append(nd[cur+1:cur+1+l].decode('mac_roman'));cur+=l+1
op=lambda c,v:encode(c,1 if v<256 else 2,v)
named=lambda c,s:op(c,names.index(s))
def patch_handler(resource,name,code):
 _,ln,off=res[resource];s=movie[off+8:off+8+ln];cnt,tab=struct.unpack_from('>HI',s,72)
 for j in range(cnt):
  rec=tab+j*46
  if struct.unpack_from('>H',s,rec)[0]!=names.index(name):continue
  size,start=struct.unpack_from('>II',s,rec+4);assert len(code)<=size
  exe[base+off+8+start:base+off+8+start+size]=code+b'\x00'*(size-len(code))
  struct.pack_into('>I',exe,base+off+8+rec+4,len(code));return
 raise ValueError(name)
_,ln,off=res[1078];s=movie[off+8:off+8+ln];original=s[1294:1294+542]
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(35);port=listener.getsockname()[1]
# Literal zero is the fixed server host. Keep the original resource size.
lt,tab=struct.unpack_from('>HI',s,78);data=struct.unpack_from('>I',s,88)[0];_,at=struct.unpack_from('>II',s,tab)
struct.pack_into('>I',exe,base+off+8+data+at,10);exe[base+off+8+data+at+4:base+off+8+data+at+14]=b'127.0.0.1\0'
tail=original[505:].replace(bytes.fromhex('ae065a'),encode(0x6e,2,port))
setup=original[:5]+original[70:127]+encode(0x6f,4,123456)+op(0x43,1)+named(0x57,'string')+named(0x4f,'userID')+tail
patch_handler(1078,'makeAServerConnection',setup)
patch_handler(1060,'prepareMovie',op(0x42,0)+named(0x57,'makeAServerConnection')+b'\x01')
# Real native EncryptString + real native Multiuser serialization. No chat
# terms are accepted; this is a transport fixture with no public connection.
cipher=op(0x44,20)+named(0x49,'userID')+op(0x43,1)+named(0x57,'string')+op(0x43,2)+op(0x56,20)
content=named(0x49,'userID')+cipher+op(0x43,2)+b'\x1e'
send=named(0x49,'gmultiuserinstance')+op(0x44,0)+op(0x44,7)+content+op(0x42,4)+named(0x67,'sendNetMessage')+b'\x01'
incoming=op(0x4b,1)+named(0x61,'content')+op(0x41,2)+op(0x43,2)+named(0x57,'getAt')
plain=incoming+named(0x49,'userID')+op(0x43,1)+named(0x57,'string')+op(0x43,2)+op(0x56,21)
reply=named(0x49,'gmultiuserinstance')+op(0x44,0)+op(0x44,7)+named(0x49,'userID')+plain+op(0x43,2)+b'\x1e'+op(0x42,4)+named(0x67,'sendNetMessage')+b'\x01'
condition=op(0x4b,1)+named(0x61,'subject')+op(0x44,7)+b'\x0f'
callback=condition+op(0x55,len(reply)+2)+reply+send
patch_handler(1078,'DefaultMessageHandler',callback)
(out/'probe.exe').write_bytes(exe)
for name in ['Dirapi.dll','Iml32.dll','Proj.dll','msvcp100.dll','msvcr100.dll','Xtras']:
 p=out/name
 if p.is_symlink():p.unlink()
 if not p.exists():p.symlink_to(root/name)
def string(b):return struct.pack('!I',len(b))+b+b'\0'*(len(b)%2)
def frame(subject,content):
 p=struct.pack('!iI',0,0)+string(subject)+string(b'System')+struct.pack('!I',1)+string(b'*')+content
 return b'\x72\0'+struct.pack('!I',len(p))+p
def read(c,n):
 b=b''
 while len(b)<n:
  r=c.recv(n-len(b))
  if not r:raise EOFError()
  b+=r
 return b
env=dict(os.environ,WINEPREFIX=str(out/'wine-prefix'),WINEDEBUG='-all',WINEDLLOVERRIDES='mscoree,mshtml=')
log=open(out/'wine.log','w')
p=subprocess.Popen(['wine',str(out/'probe.exe')],cwd=out,env=env,stdout=log,stderr=log)
try:
 c,_=listener.accept();c.settimeout(12)
 with c:
  head=read(c,6);first=read(c,struct.unpack('!I',head[2:])[0]);print('Native connected to loopback fixture',flush=True)
  c.sendall(frame(b'Logon',struct.pack('!H',3)+string(b'Local compatibility fixture')))
  head=read(c,6);packet=read(c,struct.unpack('!I',head[2:])[0]);(out/'native-packet.bin').write_bytes(head+packet)
  print(json.dumps({'packet_bytes':len(packet),'packet_hex':packet.hex()}),flush=True)
  from chat_protocol import translate_chat_packet
  sys.path.insert(0,str(root/'browser-test/tests'))
  from test_chat_protocol import RAW_CIPHER,packet as chat_packet
  def text_field(payload):
   def string_at(at):
    n=struct.unpack_from('!I',payload,at)[0];return payload[at+4:at+4+n],at+4+n+n%2
   _,at=string_at(8);_,at=string_at(at);count=struct.unpack_from('!I',payload,at)[0];at+=4
   for _ in range(count):_,at=string_at(at)
   at+=8;_,at=string_at(at);value,_=string_at(at+2);return value
  results={}
  for label,body in [('original-browser',chat_packet(RAW_CIPHER)),('fixed-browser',translate_chat_packet(chat_packet(RAW_CIPHER),'client'))]:
   c.sendall(b'\x72\0'+struct.pack('!I',len(body))+body)
   header=read(c,6);response=read(c,struct.unpack('!I',header[2:])[0])
   decoded=text_field(response)
   results[label]={'native_decoded_hex':decoded.hex(),'matches_plaintext':decoded==b'MoonBase0429'}
  print(json.dumps(results),flush=True)
  (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
  assert not results['original-browser']['matches_plaintext']
  assert results['fixed-browser']['matches_plaintext']
finally:
 p.terminate();listener.close();log.close()
 subprocess.run(['wineserver','-k'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
