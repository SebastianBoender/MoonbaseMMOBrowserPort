"""Measure the original vehicle under Wine against an isolated loopback fixture."""
import argparse,hashlib,json,os,socket,struct,subprocess,sys,time
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path,help='Original package directory (read-only)')
parser.add_argument('--output',type=Path,required=True,help='Disposable Wine prefix and fixture output')
parser.add_argument('--details',action='store_true',help='Also capture native centers of mass')
parser.add_argument('--materials',action='store_true',help='Read native Car/Spring/ground friction values')
parser.add_argument('--contacts',action='store_true',help='Also capture the native collision list')
parser.add_argument('--friction-body',choices=['car','GroundShape'],default='car')
parser.add_argument('--friction-percent','--car-friction-percent',dest='friction_percent',type=int,choices=range(101),metavar='0..100',help='Override chassis friction for a contact micro-test')
parser.add_argument('--frames',type=int,default=180)
parser.add_argument('--step-seconds',type=float,default=0.022)
parser.add_argument('--spring-offset',type=int,default=10,help='Initial vertical separation for suspension micro-tests (0–255)')
parser.add_argument('--input',choices=['idle','forward','reverse','left','right','brake','forward-left','forward-right','forward-brake'],default='forward')
args=parser.parse_args()
if not 0 < args.frames <= 10000 or not 0 < args.step_seconds <= 0.1 or not 0 <= args.spring_offset <= 255:
 parser.error('Use 1–10000 frames and a step greater than zero, at most 0.1 seconds')
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
extra_names=[name for name, enabled in [('centerOfMass',args.details),('collisionList',args.contacts)] if enabled and name not in names]
if extra_names:
 names.extend(extra_names);new=bytearray(nd[:20])
 for name in names:
  encoded=name.encode('mac_roman');new.extend(bytes([len(encoded)])+encoded)
 new.extend(nd[cur:]);struct.pack_into('>H',new,18,len(names))
 for pos in [8,12]:struct.pack_into('>I',new,pos,struct.unpack_from('>I',nd,pos)[0]+len(new)-len(nd))
 if len(exe)%2:exe.append(0)
 at=len(exe);exe.extend(b'manL'+struct.pack('<I',len(new))+new)
 entry=base+mm+8+h+1059*st;struct.pack_into('<II',exe,entry+4,len(new),at)
 struct.pack_into('<I',exe,base+4,len(exe)-base-8)
op=lambda c,v:encode(c,1 if v<256 else 2,v)
named=lambda c,s:op(c,names.index(s))
def patch_handler(resource,name,code):
 entry=base+mm+8+h+resource*st
 ln,absolute=struct.unpack_from('<II',exe,entry+4)
 s=bytes(exe[absolute+8:absolute+8+ln]);cnt,tab=struct.unpack_from('>HI',s,72)
 for j in range(cnt):
  rec=tab+j*46
  if struct.unpack_from('>H',s,rec)[0]!=names.index(name):continue
  size,start=struct.unpack_from('>II',s,rec+4)
  if len(code)>size:
   raise ValueError(f'{name}: fixture exceeds original {size}-byte capacity')
  exe[absolute+8+start:absolute+8+start+size]=code+b'\x00'*(size-len(code))
  struct.pack_into('>I',exe,absolute+8+rec+4,len(code))
  return
 raise ValueError(name)
_,ln,off=res[1078];s=movie[off+8:off+8+ln];original=s[1294:1294+542]
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(60);port=listener.getsockname()[1]
# Literal zero is the fixed server host. Keep the original resource size.
lt,tab=struct.unpack_from('>HI',s,78);data=struct.unpack_from('>I',s,88)[0];_,at=struct.unpack_from('>II',s,tab)
struct.pack_into('>I',exe,base+off+8+data+at,10);exe[base+off+8+data+at+4:base+off+8+data+at+14]=b'127.0.0.1\0'
tail=original[505:].replace(bytes.fromhex('ae065a'),encode(0x6e,2,port))
setup=original[:5]+original[70:127]+encode(0x6f,4,123456)+op(0x43,1)+named(0x57,'string')+named(0x4f,'userID')+tail
patch_handler(1078,'makeAServerConnection',setup)
patch_handler(1060,'prepareMovie',op(0x42,0)+named(0x57,'makeAServerConnection')+b'\x01')

# The original world, asset construction and Havok setup still run. No terms
# are accepted; all network traffic is confined to this loopback fixture.
patch_handler(1078,'DefaultMessageHandler',op(0x41,1)+named(0x4f,'OnlineConnection')+op(0x41,5)+op(0x42,1)+named(0x57,'go')+b'\x01')
_,ln,off=res[1077];script=movie[off+8:off+8+ln];count,table=struct.unpack_from('>HI',script,72)
handlers={}
for i in range(count):
 rec=table+i*46;ni=struct.unpack_from('>H',script,rec)[0];sz,at=struct.unpack_from('>II',script,rec+4);handlers[names[ni]]=(i,script[at:at+sz])
patch_handler(1077,'beginSprite',handlers['beginSprite'][1][:1134]+b'\x01')
lc,lt=struct.unpack_from('>HI',script,78);ld=struct.unpack_from('>I',script,88)[0]
# Preserve the original step expression while varying only its time literal.
for i in range(lc):
 kind,at=struct.unpack_from('>II',script,lt+8*i)
 if kind==9 and struct.unpack_from('>d',script,ld+at+4)[0]==0.022:
  struct.pack_into('>d',exe,base+off+8+ld+at+4,args.step_seconds)
def literal(text):
 for i in range(lc):
  kind,at=struct.unpack_from('>II',script,lt+8*i)
  if kind!=1:continue
  sz=struct.unpack_from('>I',script,ld+at)[0]
  if script[ld+at+4:ld+at+3+sz]==text.encode('mac_roman'):return op(0x44,i)
 raise ValueError(text)
def body(name):return named(0x49,'havok')+literal(name)+op(0x43,2)+named(0x67,'RigidBody')
drive=bytearray(handlers['DrivePlayer'][1])
from compatibility import decode
instructions=decode(drive)
selected={key for part in args.input.split('-') if (key:={'forward':126,'reverse':125,'left':123,'right':124,'brake':' '}.get(part)) is not None}
for i,o in enumerate(instructions):
 if o['op']!=0x57 or names[o['value']]!='keyPressed':continue
 start=instructions[i-2]['pos'];raw=drive[start:o['pos']+len(o['raw'])];assert len(raw)==7
 key=instructions[i-2]['value'];is_space=instructions[i-2]['op']==0x44
 pressed=(' ' in selected and is_space) or (not is_space and key in selected)
 # A same-size constant expression preserves all branch offsets.
 drive[start:start+7]=bytes([0x41,0 if pressed else 1,0x14,0x03,0x05,0x03,0x05])
patch_handler(1077,'DrivePlayer',drive)
suspension=bytearray(handlers['SetupPhysics'][1])
assert suspension[125:127]==bytes([0x41,10])
suspension[126]=args.spring_offset
if args.friction_percent is not None:
 if args.input != 'idle' or args.frames > 24:
  raise SystemExit('Friction micro-tests require idle input and at most 24 frames')
 # Reuse the existing Walk-friction assignment without growing SetupPhysics.
 # Its shared 0.1 literal also appears in drive/grip rules, so this probe is
 # restricted to the initial idle fall, before the first ground response.
 old=body('Walk')+op(0x44,39)+named(0x62,'friction')
 new=body(args.friction_body)+op(0x44,39)+named(0x62,'friction')
 assert old in suspension and len(old)==len(new)
 suspension=suspension.replace(old,new)
 kind,at=struct.unpack_from('>II',script,lt+8*39)
 assert kind==9 and struct.unpack_from('>d',script,ld+at+4)[0]==0.1
 struct.pack_into('>d',exe,base+off+8+ld+at+4,args.friction_percent/100)
patch_handler(1077,'SetupPhysics',suspension)
tick=named(0x49,'RoomNumber')
step=tick+op(0x41,1)+b'\x05'+named(0x4f,'RoomNumber')+op(0x41,1)+named(0x50,'FrameMod')
step+=op(0x42,0)+op(0x56,handlers['DrivePlayer'][0])+handlers['prepareFrame'][1][220:237]
fields=[tick]
for name in ['car','Spring']:
 for prop in ['position','linearVelocity','angularVelocity','rotation']+(['centerOfMass'] if args.details else []):
  fields.append(body(name)+named(0x61,prop)+op(0x43,1)+named(0x57,'string'))
if args.materials:
 for name in ['car','Spring','GroundShape']:
  fields.append(body(name)+named(0x61,'friction')+op(0x43,1)+named(0x57,'string'))
if args.contacts:fields.append(named(0x49,'havok')+named(0x61,'collisionList')+op(0x43,1)+named(0x57,'string'))
content=b''.join(fields)+op(0x43,len(fields))+b'\x1e'
step+=named(0x49,'gmultiuserinstance')+literal('car')+literal('car')+content+op(0x42,4)+named(0x67,'sendNetMessage')
step=named(0x49,'OnlineConnection')+op(0x55,len(step)+3)+step+b'\x01'
patch_handler(1077,'prepareFrame',step)
(out/'probe.exe').write_bytes(exe)
for name in ['Dirapi.dll','Iml32.dll','Proj.dll','msvcp100.dll','msvcr100.dll','Xtras']:
 p=out/name
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
def parse_packet(p):
 def text(at):
  n=struct.unpack_from('!I',p,at)[0];return p[at+4:at+4+n].decode('mac_roman'),at+4+n+n%2
 _,at=text(8);_,at=text(at);count=struct.unpack_from('!I',p,at)[0];at+=4
 for _ in range(count):_,at=text(at)
 def datum(at):
  kind=struct.unpack_from('!H',p,at)[0];at+=2
  if kind==1:return struct.unpack_from('!i',p,at)[0],at+4
  if kind==3:return text(at)
  if kind==7:
   n=struct.unpack_from('!I',p,at)[0];at+=4;values=[]
   for _ in range(n):v,at=datum(at);values.append(v)
   return values,at
  raise ValueError((kind,at,p.hex()))
 return datum(at)[0]
env=dict(os.environ,WINEPREFIX=str(out/'wine-prefix'),WINEDEBUG='-all',WINEDLLOVERRIDES='mscoree,mshtml=')
log=open(out/'wine.log','w');p=subprocess.Popen(['wine',str(out/'probe.exe')],cwd=out,env=env,stdout=log,stderr=log)
try:
 c,_=listener.accept();c.settimeout(20)
 with c:
  head=read(c,6);read(c,struct.unpack('!I',head[2:])[0]);print('Native vehicle connected',flush=True)
  c.sendall(frame(b'Logon',struct.pack('!H',3)+string(b'Local physics fixture')))
  samples=[]
  for i in range(args.frames):
   head=read(c,6);packet=read(c,struct.unpack('!I',head[2:])[0]);sample=parse_packet(packet);samples.append(sample)
   if i%30==0:print(json.dumps(sample),flush=True)
  (out/'driving-results.json').write_text(json.dumps({'input':args.input,'dt':args.step_seconds,'details':args.details,'spring_offset':args.spring_offset,'contacts':args.contacts,'materials':args.materials,'friction_override':({'body':args.friction_body,'coefficient':args.friction_percent/100} if args.friction_percent is not None else None),'samples':samples},indent=2)+'\n')
finally:
 p.terminate();listener.close();log.close()
 subprocess.run(['wineserver','-k'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
