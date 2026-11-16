const {test}=require('node:test');
const assert=require('node:assert/strict');
const {runInNewContext}=require('node:vm');
const {readFileSync}=require('node:fs');
const path=require('node:path');
function environment(){
  let wheel,prevented=0,state={movie_loaded:true,current_frame:5,is_paused:false};
  const window={__vm:{mcp_get_execution_state:()=>JSON.stringify(state)}};
  runInNewContext(readFileSync(path.join(__dirname,'../public/camera-zoom.js'),'utf8'),{window,Float32Array,document:{getElementById:()=>({addEventListener:(type,fn,options)=>{assert.equal(options.passive,false);wheel=fn}})}});
  return {window,zoom:window.moonbaseZoom,state,wheel(deltaY,extra={}){wheel({deltaY,deltaMode:0,target:{closest:s=>s==='canvas'?{}:null},preventDefault(){prevented++},...extra})},get prevented(){return prevented}};
}
test('wheel clamps view to 50–100% and never mutates the original projection',()=>{
  const e=environment(),matrix=new Float32Array([2,0,0,0,0,3,0,0,0,0,-1,-1,0,0,-2,0]);
  assert.equal(e.zoom.projection(matrix),matrix);
  for(let n=0;n<10;n++)e.wheel(120);
  assert.equal(e.zoom.scale,.5);const adjusted=e.zoom.projection(matrix);
  assert.equal(adjusted[0],1);assert.equal(adjusted[5],1.5);assert.equal(matrix[0],2);
  for(let n=0;n<16;n++)if(n!==0&&n!==5)assert.equal(adjusted[n],matrix[n]);
  for(let n=0;n<20;n++)e.wheel(-120);assert.equal(e.zoom.scale,1);
});
test('ignores login, paused state, chat, browser pinch and invalid wheel deltas',()=>{
  const e=environment();e.state.current_frame=2;e.wheel(120);e.state.current_frame=5;e.state.is_paused=true;e.wheel(120);
  e.state.is_paused=false;e.wheel(120,{ctrlKey:true});e.wheel(120,{metaKey:true});e.wheel(NaN);
  e.wheel(120,{target:{closest:()=>({})}});
  assert.equal(e.zoom.scale,1);assert.equal(e.prevented,0);
});
test('line and pixel wheels agree; high resolution trackpad deltas accumulate',()=>{
  const a=environment(),b=environment();a.wheel(3,{deltaMode:1});b.wheel(48);assert.equal(a.zoom.scale,b.zoom.scale);
  const c=environment();for(let n=0;n<10;n++)c.wheel(4.8);assert.ok(Math.abs(c.zoom.scale-b.zoom.scale)<1e-10);
});
test('GPU upload and observed nameplate camera use the same adjusted projection',()=>{
  const e=environment(),uploads=[];
  class GL{constructor(){this.canvas={getAttribute:()=> '1'}}}
  for(const name of ['bindFramebuffer','shaderSource','useProgram','viewport','drawElements'])GL.prototype[name]=function(){};
  GL.prototype.getUniformLocation=function(program,name){return {name}};
  GL.prototype.uniformMatrix4fv=function(...args){uploads.push(args)};
  e.window.WebGL2RenderingContext=GL;
  runInNewContext(readFileSync(path.join(__dirname,'../public/gpu-compatibility.js'),'utf8'),{window:e.window,location:{search:''},URLSearchParams,performance:{now:()=>0},document:{hidden:false},console});
  const gl=new GL(),program={};gl.useProgram(program);gl.viewport(0,0,800,550);
  const view=new Float32Array(16).fill(1),projection=new Float32Array(16).fill(2);projection[15]=0;projection[11]=-1;
  const v=gl.getUniformLocation(program,'u_view'),p=gl.getUniformLocation(program,'u_projection');
  for(let n=0;n<10;n++)e.wheel(120);
  gl.uniformMatrix4fv(v,false,view);gl.uniformMatrix4fv(p,false,projection);gl.drawElements(4,500,0,0);
  assert.equal(uploads.at(-1)[2][0],1);assert.equal(projection[0],2);
  const ortho=new Float32Array(16).fill(2);ortho[15]=1;gl.uniformMatrix4fv(p,false,ortho);assert.equal(uploads.at(-1)[2],ortho);
  assert.equal(e.window.moonbaseGPU.camera.projection[0],1);assert.equal(e.window.moonbaseGPU.camera.view[0],1);
});
