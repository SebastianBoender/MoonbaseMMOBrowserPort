const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname,'../public/touch-controls.js'),'utf8');
function environment() {
  const elements = {}, listeners = {}, docEvents = {}, messages = [], intervals = [];
  function element(id) {
    if(elements[id]) return elements[id];
    const events = {}, classes = new Set();
    return elements[id] = {hidden:false,checked:false,disabled:false,value:'',textContent:'',dataset:{},events,
      classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},setPointerCapture(){},
      addEventListener:(type,fn)=>(events[type]??=[]).push(fn),
      querySelector:()=>element(id+'-button'),querySelectorAll:()=>[],focus(){},blur(){},
      fire(type,opts={}){for(const fn of events[type]||[])fn({button:0,pointerId:1,preventDefault(){},...opts});}};
  }
  const keys=['forward','back','left','right','jetpack','dance','brake','exit'].map(key=>{const e=element(key);e.dataset.gameKey=key;return e;});
  element('touch-controls').querySelectorAll=()=>keys;
  const child={postMessage:data=>messages.push(JSON.parse(JSON.stringify(data)))};
  element('game').contentWindow=child;
  runInNewContext(source,{document:{hidden:false,getElementById:element,addEventListener:(type,fn)=>docEvents[type]=fn},location:{origin:'https://moonbasemmo.com'},matchMedia:()=>({matches:true,addEventListener(){}}),setInterval:fn=>intervals.push(fn),addEventListener:(type,fn)=>listeners[type]=fn});
  const state=(mode='Walking')=>listeners.message({origin:'https://moonbasemmo.com',source:child,data:{type:'moonbase-touch-state',loaded:true,frame:5,mode}});
  state(); messages.length=0;
  return {element,messages,state,fire:type=>listeners[type](),tick:()=>intervals.forEach(fn=>fn())};
}
test('independent fingers hold movement and jetpack; cancelling one preserves the other',()=>{
  const e=environment();e.element('forward').fire('pointerdown',{pointerId:1});e.element('jetpack').fire('pointerdown',{pointerId:2});
  assert.deepEqual(e.messages.at(-1).keys,['forward','jetpack']);
  e.element('forward').fire('pointercancel',{pointerId:1});assert.deepEqual(e.messages.at(-1).keys,['jetpack']);
  e.element('jetpack').fire('lostpointercapture',{pointerId:2});assert.deepEqual(e.messages.at(-1).keys,[]);
});
test('two fingers on the same key require both releases; blur clears heartbeat state',()=>{
  const e=environment();const forward=e.element('forward');forward.fire('pointerdown',{pointerId:1});forward.fire('pointerdown',{pointerId:2});
  forward.fire('pointerup',{pointerId:1});assert.deepEqual(e.messages.at(-1).keys,['forward']);
  e.fire('blur');assert.equal(e.messages.at(-1).action,'release');const count=e.messages.length;e.tick();assert.equal(e.messages.length,count);
});
test('mode changes disable incompatible actions; stale reload resets pending forms',()=>{
  const e=environment();assert.equal(e.element('brake').disabled,true);e.state('Driving');assert.equal(e.element('jetpack').disabled,true);assert.equal(e.element('brake').disabled,false);
  e.element('touch-name-form').fire('submit');assert.equal(e.element('touch-name-form-button').disabled,true);
  e.element('game').fire('load');assert.equal(e.element('touch-name-form-button').disabled,false);assert.equal(e.element('touch-chat-form').hidden,true);
});
