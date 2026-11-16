const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const config=require('../public/resolution.js');
test('presets retain authored framing and do not multiply by device pixel ratio',()=>{
  assert.deepEqual(Object.values(config.presets).map(p=>[p.width,p.height]),[[800,550],[1047,720],[1571,1080],[2095,1440],[3142,2160]]);
  for(const p of Object.values(config.presets))assert.ok(Math.abs(p.width/p.height-16/11)<.001);
  assert.throws(()=>config.preset('__proto__'));
});
test('texture, depth buffer and viewport limits each constrain quality',()=>{
  const limits={texture:4096,renderbuffer:4096,viewport:[4096,4096]};
  assert.equal(config.supported('4k',limits),true);
  for(const limited of [{...limits,texture:2048},{...limits,renderbuffer:2048},{...limits,viewport:[2048,4096]}])assert.equal(config.supported('4k',limited),false);
});
test('input and overlay conversion map render pixels back to authored coordinates',()=>{
  const canvas={width:3142,height:2160};const window={};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/coordinates.js'),'utf8'),{window,document:{querySelector:()=>canvas}});
  const c=window.moonbaseCoordinates;
  assert.deepEqual(Array.from(c.logicalToRender(400,275)),[1571,1080]);
  const viewport=c.viewport({canvas,viewport:[0,0,3142,2160]});assert.equal(viewport.width,800);assert.equal(viewport.height,550);
  const setup=c.viewport({canvas,viewport:[0,0,543*3142/800,2160]});assert.ok(Math.abs(setup.width-543)<1e-9);
});
test('performance summary exposes stalls instead of hiding them in average fps',()=>{
  const stats=config.summary([10,10,10,100]);assert.equal(stats.median,10);assert.equal(stats.p95,100);assert.equal(stats.longFrames,1);
});
function environment(client='modern',initial='original',max=4096){
  const events={},docEvents={},canvasEvents={},messages=[],calls=[];
  const canvas={width:800,height:550,addEventListener:(type,fn)=>canvasEvents[type]=fn,getContext:()=>gl};
  const gl={MAX_TEXTURE_SIZE:1,MAX_RENDERBUFFER_SIZE:2,MAX_VIEWPORT_DIMS:3,isContextLost:()=>false,getParameter:p=>p===3?[max,max]:max};
  const parent={postMessage:data=>messages.push(data)};
  const document={hidden:false,documentElement:{dataset:{}},dispatchEvent(){},addEventListener:(type,fn)=>docEvents[type]=fn};
  const window={moonbaseResolution:config,moonbaseCoordinates:{canvas:()=>canvas},moonbaseGPU:{frameTimes:[],resetTimings(){}},__vm:{set_stage_size:(w,h)=>{calls.push([w,h]);canvas.width=w;canvas.height=h;},set_renderer_backend:()=>calls.push(['restore'])}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/resolution-player.js'),'utf8'),{window,document,parent,location:{origin:'https://moonbasemmo.com',search:`?client=${client}&resolution=${initial}`},URLSearchParams,performance:{now:()=>0},Event:class{},setTimeout:fn=>{fn();},setInterval(){},addEventListener:(type,fn)=>events[type]=fn});
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  const load=async()=>{events['moonbase-runtime']({detail:{kind:'movie-loaded'}});await flush();};
  const request=async(id,origin='https://moonbasemmo.com',source=parent)=>{events.message({origin,source,data:{type:'moonbase-resolution',resolution:id}});await flush();};
  return {calls,messages,canvas,canvasEvents,events,load,request,flush};
}
test('Modern changes backing resolution without touching game state; Original stays fixed',async()=>{
  const e=environment();await e.load();await e.request('1080p');assert.deepEqual(e.calls.at(-1),[1571,1080]);assert.equal(e.messages.at(-1).selected,'1080p');
  const original=environment('original','4k');await original.load();await original.request('4k');assert.deepEqual(original.calls,[]);
});
test('unsupported resolution restores prior quality; untrusted and invalid requests are ignored',async()=>{
  const e=environment('modern','720p',2048);await e.load();await e.request('4k');assert.equal(e.messages.at(-1).selected,'720p');assert.equal(e.messages.at(-1).error,true);
  const count=e.calls.length;await e.request('1080p','https://evil.example');await e.request('1080p',undefined,{});await e.request('__proto__');assert.equal(e.calls.length,count);
});
test('GPU allocation failure during a switch rolls back to the working target',async()=>{
  const e=environment();await e.load();await e.request('1080p');
  e.events['moonbase-render-error']({detail:'[3D] Render failed: incomplete 3D framebuffer'});
  assert.deepEqual(e.calls.at(-1),[800,550]);assert.equal(e.messages.at(-1).error,true);
});
