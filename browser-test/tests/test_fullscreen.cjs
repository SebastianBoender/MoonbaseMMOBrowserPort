const {test}=require('node:test');
const assert=require('node:assert/strict');
const {runInNewContext}=require('node:vm');
const {readFileSync}=require('node:fs');
const source=readFileSync(require('node:path').join(__dirname,'../public/fullscreen.js'),'utf8');
function environment(native) {
  const nodes={},events={},windowEvents={};
  const node=id=>nodes[id]??=( ()=>{const classes=new Set();return {classList:{toggle:(name,on)=>on?classes.add(name):classes.delete(name),contains:name=>classes.has(name)},attributes:{},checked:false,addEventListener(type,fn){this[type]=fn},setAttribute(name,value){this.attributes[name]=value},focus(){this.focused=true},click(){this.checked=!this.checked;this.change?.()}}})();
  const doc={getElementById:node,documentElement:node('html'),activeElement:node('previous'),addEventListener:(type,fn)=>events[type]=fn,dispatchEvent(){}};
  node('game').contentWindow={};
  if(native==='ok') {node('play-surface').requestFullscreen=async()=>{doc.fullscreenElement=node('play-surface');events.fullscreenchange()};doc.exitFullscreen=async()=>{doc.fullscreenElement=null;events.fullscreenchange()};}
  if(native==='reject')node('play-surface').requestFullscreen=async()=>{throw Error('denied')};
  runInNewContext(source,{document:doc,location:{origin:'https://moonbasemmo.com'},Event:class{},addEventListener:(type,fn)=>windowEvents[type]=fn});
  return {node,doc,events,windowEvents,active:()=>node('play-surface').classList.contains('is-fullscreen')};
}
test('native fullscreen exits and restores focus; touch toggle works inside it',async()=>{
  const e=environment('ok');await e.node('fullscreen').click();assert.equal(e.active(),true);
  e.node('fullscreen-touch').click();assert.equal(e.node('touch-toggle').checked,true);
  await e.node('exit-fullscreen').click();assert.equal(e.active(),false);assert.equal(e.node('previous').focused,true);
});
test('missing or rejected APIs fall back and Escape exits',async()=>{
  for(const native of ['missing','reject']){const e=environment(native);await e.node('fullscreen').click();assert.equal(e.active(),true);e.events.keydown({key:'Escape'});assert.equal(e.active(),false);}
});
test('only same-origin game iframe can request Escape from fallback',async()=>{
  const e=environment('missing');await e.node('fullscreen').click();
  const message={data:{type:'moonbase-exit-fullscreen'},source:e.node('game').contentWindow,origin:'https://evil.example'};
  e.windowEvents.message(message);assert.equal(e.active(),true);
  message.origin='https://moonbasemmo.com';e.windowEvents.message(message);assert.equal(e.active(),false);
});
