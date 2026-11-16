const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../public/touch-input.js'), 'utf8');
function environment() {
  const listeners = {}, pointer = {}, doc = {}, intervals = [], calls = [], parent = {};
  let now = 1000, mode = 'Walking', frame = 5, paused = false;
  const rect = {left:10, top:20, width:320, height:220, right:330, bottom:240};
  const canvas = {width:800, height:550, getBoundingClientRect:() => rect};
  const mount = {querySelector:() => canvas, setPointerCapture() {}, addEventListener:(type,fn) => pointer[type]=fn};
  const vm = {
    mcp_get_execution_state:() => JSON.stringify({movie_loaded:true,current_frame:frame,is_paused:paused}),
    key_down:(...args) => calls.push(['down',...args]), key_up:(...args) => calls.push(['up',...args]),
    mouse_move:(...args) => calls.push(['move',...args]), mouse_down:(...args) => calls.push(['mouseDown',...args]), mouse_up:(...args) => calls.push(['mouseUp',...args]),
  };
  const document = {hidden:false,getElementById:() => mount,addEventListener:(type,fn) => doc[type]=fn};
  const window = {__vm:vm,moonbaseRead:{globals:() => ({AvatarMode:{value:mode}}),string:d => d?.value || ''}};
  parent.postMessage=()=>{};
  runInNewContext(source,{window,document,parent,location:{origin:'https://moonbasemmo.com'},Date:{now:()=>now},setInterval:fn=>intervals.push(fn),setTimeout:fn=>fn(),addEventListener:(type,fn)=>listeners[type]=fn});
  const message = async (data,origin='https://moonbasemmo.com',sender=parent) => listeners.message({data:{type:'moonbase-touch',...data},origin,source:sender});
  const point = (type,overrides={}) => {
    const event={pointerId:1,button:0,clientX:170,clientY:130,target:{closest:()=>null},preventDefault(){},stopImmediatePropagation(){},...overrides};
    pointer[type](event);
  };
  return {calls,message,point,rect,document,fire:type=>listeners[type](),hide:()=>{document.hidden=true;doc.visibilitychange();},tick:()=>intervals.forEach(fn=>fn()),advance:t=>now+=t,setMode:m=>mode=m,setFrame:f=>frame=f,setPaused:p=>paused=p};
}
test('independent held arrows and jetpack, with no repeated downs on heartbeats', async () => {
  const e=environment(); await e.message({action:'enabled',enabled:true});
  await e.message({action:'keys',keys:['forward','jetpack']});
  await e.message({action:'keys',keys:['forward','jetpack']});
  assert.deepEqual(e.calls,[['down','ArrowUp',38],['down','Control',17]]);
  await e.message({action:'keys',keys:['jetpack']});
  assert.deepEqual(e.calls.at(-1),['up','ArrowUp',38]);
  await e.message({action:'release'}); assert.deepEqual(e.calls.at(-1),['up','Control',17]);
});
test('cancelled input, lost parent heartbeat, blur, hidden page and mode changes release keys', async () => {
  for(const reason of ['release','timeout','blur','hidden','mode','paused','disabled']) {
    const e=environment(); await e.message({action:'enabled',enabled:true}); await e.message({action:'keys',keys:['forward']});
    if(reason==='release') await e.message({action:'release'});
    if(reason==='timeout'){e.advance(1300);e.tick();}
    if(reason==='blur')e.fire('blur');
    if(reason==='hidden')e.hide();
    if(reason==='mode'){e.setMode('CharacterSetup');e.tick();}
    if(reason==='paused'){e.setPaused(true);e.tick();}
    if(reason==='disabled')await e.message({action:'enabled',enabled:false});
    assert.deepEqual(e.calls.at(-1),['up','ArrowUp',38],reason);
  }
});
test('foreign origins, non-parent messages, unknown keys and keys outside gameplay are rejected', async () => {
  const e=environment(); await e.message({action:'enabled',enabled:true});
  await e.message({action:'keys',keys:['forward']},'https://evil.example');
  await e.message({action:'keys',keys:['forward']},undefined,{});
  await e.message({action:'keys',keys:['__proto__','constructor','bogus']});
  e.setFrame(2);await e.message({action:'keys',keys:['forward','jetpack']});
  assert.deepEqual(e.calls,[]);
});
test('vehicle mode accepts steering/brake/exit and excludes rocket/dance', async () => {
  const e=environment();e.setMode('Driving');await e.message({action:'enabled',enabled:true});
  await e.message({action:'keys',keys:['left','brake','exit','jetpack','dance']});
  assert.deepEqual(e.calls,[['down','ArrowLeft',37],['down',' ',32],['down','=',187]]);
});
test('scaled canvas taps map to original 800 by 550 coordinates and cancel safely', () => {
  const e=environment();e.point('pointerdown');
  assert.deepEqual(e.calls,[['move',400,275],['mouseDown',400,275]]);
  e.point('pointermove',{clientX:210}); assert.deepEqual(e.calls.at(-1),['move',500,275]);
  e.point('pointercancel',{clientX:210}); assert.deepEqual(e.calls.at(-1),['mouseUp',500,275]);
  const count=e.calls.length;e.point('lostpointercapture');assert.equal(e.calls.length,count);
});
test('holding a scaled pointer is not cancelled by keyboard watchdog or parent release', async () => {
  const e=environment();e.point('pointerdown');e.advance(5000);e.tick();await e.message({action:'release'});
  assert.equal(e.calls.filter(c=>c[0]==='mouseUp').length,0);
  e.fire('blur');assert.equal(e.calls.filter(c=>c[0]==='mouseUp').length,1);
});
test('unscaled desktop events and player overlay buttons retain native handling', () => {
  const e=environment();e.rect.width=800;e.rect.height=550;e.point('pointerdown');assert.deepEqual(e.calls,[]);
  const f=environment();f.point('pointerdown',{target:{closest:()=>({})}});assert.deepEqual(f.calls,[]);
});
