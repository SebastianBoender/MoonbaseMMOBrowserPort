"""Build an isolated fixed-step browser driving fixture; never modify production assets.

Run after setup.py. Serve OUTPUT with serve.py, open Player diagnostics and
Trace world startup, click Play, then read RoomNumber and rigid body properties
in the Lingo console. The fixture stops after 90 physics steps. --native uses
original vehicle handlers to expose emulator errors instead of the fallback.
"""
import argparse,sys,struct,shutil,json,hashlib
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--native',action='store_true');parser.add_argument('--runtime-bundle',type=Path,help='Optional experimental bundle, copied only into this fixture');parser.add_argument('--frames',type=int,default=90);parser.add_argument('--input',choices=['idle','forward','reverse','forward-left','forward-right','forward-brake'],default='forward');args=parser.parse_args()
if not 1 <= args.frames <= 10000:parser.error('frames must be between 1 and 10000')
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'browser-test'))
if args.output.resolve()==root or root in args.output.resolve().parents:raise SystemExit('Use a disposable directory outside the repository')
from compatibility import decode,encode,insert_bytecode
out=args.output.resolve();marker=out/'.moonbase-driving-fixture'
if out.exists() and any(out.iterdir()) and not marker.exists():raise SystemExit('Output must be empty or an existing driving fixture')
out.mkdir(parents=True,exist_ok=True);marker.write_text('Disposable local physics fixture\n')
pub=out/'public';pub.mkdir(parents=True,exist_ok=True)
vendor=pub/'vendor'
if vendor.is_symlink():vendor.unlink()
elif vendor.exists():shutil.rmtree(vendor)

for p in (root/'browser-test/public').iterdir():
 if p.is_file():shutil.copy2(p,pub/p.name)
for d in ['vendor','icons']:
 p=pub/d
 if not p.exists():p.symlink_to(root/'browser-test/public'/d,target_is_directory=True)
(pub/'game').mkdir(exist_ok=True)
for p in (root/'browser-test/public/game').iterdir():
 if p.is_file() and p.suffix=='.json':shutil.copy2(p,pub/'game'/p.name)
for f in ['serve.py','mus_bridge.py','chat_protocol.py']:shutil.copy2(root/'browser-test'/f,out/f)
m=bytearray((root/'browser-test/public/game/moonbase-browser.dir').read_bytes());mm=struct.unpack_from('<I',m,24)[0];h,st,_,n=struct.unpack_from('<HHII',m,mm+8);res={i:(mm+8+h+i*st,*struct.unpack_from('<4sII',m,mm+8+h+i*st)[1:]) for i in range(n)}
e,sz,off=res[1059];nd=m[off+8:off+8+sz];names=[];cur=20
for _ in range(struct.unpack_from('>H',nd,18)[0]):l=nd[cur];cur+=1;names.append(nd[cur:cur+l].decode('mac_roman'));cur+=l
op=lambda c,v:encode(c,1 if v<256 else 2,v)
named=lambda c,s:op(c,names.index(s))
baseline=(root/'browser-test/public/game/moonbase.dir').read_bytes()
_,osz,ooff=res[1077]
# Resource locations in the adapted movie point to appended scripts, so resolve
# the original movie's map independently.
omb=struct.unpack_from('<I',baseline,24)[0];oh,ost,_,_=struct.unpack_from('<HHII',baseline,omb+8)
_,osz,ooff=struct.unpack_from('<4sII',baseline,omb+8+oh+1077*ost)
oscript=baseline[ooff+8:ooff+8+osz];oc,ot=struct.unpack_from('>HI',oscript,72);original={};original_ids={}
for oi in range(oc):
 rr=ot+46*oi;ni=struct.unpack_from('>H',oscript,rr)[0];ll,aa=struct.unpack_from('>II',oscript,rr+4);original[names[ni]]=oscript[aa:aa+ll];original_ids[names[ni]]=oi
for rid in [1077,1078]:
 entry,sz,off=res[rid];s=bytearray(m[off+8:off+8+sz]);count,tab=struct.unpack_from('>HI',s,72)
 for i in range(count):
  rec=tab+i*46;name=names[struct.unpack_from('>H',s,rec)[0]];sz,start=struct.unpack_from('>II',s,rec+4);code=bytes(s[start:start+sz]);new=None
  if args.native and rid==1077 and name=='SetupPhysics':new=original[name]
  elif rid==1078 and name=='makeAServerConnection':new=b'\x01'
  elif rid==1077 and name=='FramerateTest':new=op(0x41,1)+named(0x50,'FrameMod')+b'\x01'
  elif rid==1077 and name=='beginSprite':
   # The avatar mode switch moves only the rider/camera; the two rigid bodies
   # retain their original SetupPhysics spawn state.
   old=bytes.fromhex('41034201560c');assert old in code
   code=code.replace(old,bytes.fromhex('41014201560c'))
   prefix=b'\x03'+named(0x4f,'RoomNumber')
   inserts={0:prefix}
   if args.native:
    assert code[-1:]==b'\x01'
    inserts[len(code)-1]=op(0x43,0)+b'\x1e'+named(0x4f,'browserCartYaw')
   new=insert_bytecode(code,inserts)
  elif rid==1077 and name=='DrivePlayer':
   new=bytearray(code);ops=decode(code)
   for j,o in enumerate(ops):
    if o['op']==0x57 and names[o['value']]=='keyPressed':
     at=ops[j-2]['pos'];assert o['pos']+len(o['raw'])-at==7
     selected={key for part in args.input.split('-') if (key:={'forward':126,'reverse':125,'left':123,'right':124,'brake':' '}.get(part)) is not None}
     pressed=(ops[j-2]['op']==0x41 and ops[j-2]['value'] in selected) or (ops[j-2]['op']==0x44 and ' ' in selected)
     new[at:at+7]=bytes([0x41,0 if pressed else 1,0x14,0x03,0x05,0x03,0x05])
  elif rid==1077 and name=='prepareFrame':
   if args.native:
    # Match the projector fixture exactly: original DrivePlayer then Havok
    # step, with no recovery/camera/network handlers between measured steps.
    code=op(0x41,1)+named(0x50,'FrameMod')+op(0x42,0)+op(0x56,original_ids['DrivePlayer'])+original[name][220:237]
    # Reuse the fallback-only accumulator in this native-handler test as a
    # private trace list. No production controller or network handler reads it.
    fields=[named(0x49,'RoomNumber')]
    for body_literal in [28,32]:  # original gameplay literals: car, Spring
     for prop in ['position','linearVelocity','angularVelocity','rotation']:
      fields.append(named(0x49,'havok')+op(0x44,body_literal)+op(0x43,2)+named(0x67,'rigidBody')+named(0x61,prop)+op(0x43,1)+named(0x57,'string'))
    row=b''.join(fields)+op(0x43,len(fields))+b'\x1e'
    code+=named(0x49,'browserCartYaw')+row+op(0x42,2)+named(0x57,'add')+b'\x01'
   # if count < 90 jump over return, otherwise return
   gate=named(0x49,'RoomNumber')+op(0x41,args.frames)+b'\x11'+op(0x55,3)+b'\x01'
   increment=named(0x49,'RoomNumber')+op(0x41,1)+b'\x05'+named(0x4f,'RoomNumber')
   new=insert_bytecode(code,{0:gate+increment})
  if new is not None:
   struct.pack_into('>II',s,rec+4,len(new),len(s));s.extend(new)
 for pos in [8,12]:struct.pack_into('>I',s,pos,len(s))
 if len(m)%2:m.append(0)
 at=len(m);m.extend(b'rcsL'+struct.pack('<I',len(s))+s);struct.pack_into('<II',m,entry+4,len(s),at)
struct.pack_into('<I',m,4,len(m)-8)
(pub/'game/moonbase-browser.dir').write_bytes(m)
shutil.copy2(root/'browser-test/public/game/moonbase.dir',pub/'game/moonbase.dir')
print(out)

(out/'driving-fixture.json').write_text(json.dumps({'input':args.input,'frames':args.frames,'dt':0.022,'native_handlers':args.native},indent=2)+'\n')
# Add an export action only to this private diagnostics UI. Every sample is
# recorded by the movie immediately after Havok.step; polling cannot skip ticks.
player=pub/'player.js';js=player.read_text()
if args.native:
 marker="    if (event.data.type === 'moonbase-lingo') {"
 js=js.replace(marker,marker+"""
      if (String(event.data.source).trim() === '@export-driving') {
        const size = JSON.parse(await vm.mcp_eval_lingo('browserCartYaw.count')).result_value;
        for (let i=1; i<=Number(size); i++) {
          const row = [i];
          for (let k=2; k<=9; k++) {
            const result = JSON.parse(await vm.mcp_eval_lingo(`getAt(getAt(browserCartYaw, ${i}), ${k})`));
            row.push(JSON.parse(result.result_value));
          }
          report('info', `Driving row: ${JSON.stringify(row)}`);
        }
        return;
      }
 """)
if args.runtime_bundle:
 bundle=args.runtime_bundle.resolve();official=vendor.resolve();vendor.unlink();vendor.mkdir()
 dest=vendor/'dirplayer-0.8.1';dest.mkdir()
 for asset in (official/'dirplayer-0.8.1').iterdir():
  if asset.name!='dirplayer-modern.js':(dest/asset.name).symlink_to(asset,target_is_directory=asset.is_dir())
 shutil.copy2(bundle,dest/'dirplayer-modern.js')
 # Load the supplied bundle for the Original renderer too, keeping its render
 # options original while testing exactly the same experimental physics code.
 js=js.replace('if (modern)', 'if (true)',1)
 manifest=pub/'game/modern-runtime.json';data=json.loads(manifest.read_text())
 data['bundle_sha256']=hashlib.sha256(bundle.read_bytes()).hexdigest();manifest.write_text(json.dumps(data))
player.write_text(js)
