const {test}=require('node:test');const assert=require('node:assert/strict');
const {runInNewContext}=require('node:vm');const {readFileSync}=require('node:fs');const path=require('node:path');
function environment(){
  class GL{constructor(stage=true){this.canvas={getAttribute:()=>stage?'1':null};}}
  for(const name of ['bindFramebuffer','shaderSource','getUniformLocation','useProgram','uniformMatrix4fv','viewport','drawElements','deleteFramebuffer','deleteRenderbuffer','deleteTexture'])GL.prototype[name]=function(){};
  for(const name of ['createFramebuffer','createRenderbuffer','createTexture'])GL.prototype[name]=()=>({});
  const window={WebGL2RenderingContext:GL};
  runInNewContext(readFileSync(path.join(__dirname,'../public/gpu-compatibility.js'),'utf8'),{window,location:{search:'?client=modern'},URLSearchParams,performance:{now:()=>0},document:{hidden:false},console});
  return {GL,state:window.moonbaseGPU};
}
test('context loss invalidates old accounting without subtracting restored textures',()=>{
  const {GL,state}=environment(),gl=new GL(),old=gl.createTexture();assert.equal(state.resources.textures,1);
  state.resetResources();const current=gl.createTexture();gl.deleteTexture(old);assert.equal(state.resources.textures,1);
  gl.deleteTexture(current);assert.equal(state.resources.textures,0);gl.deleteTexture(current);assert.equal(state.resources.textures,0);
});
test('only stage resources are counted; normal framebuffer replacement stays flat',()=>{
  const {GL,state}=environment(),gl=new GL(),other=new GL(false);other.createTexture();assert.equal(state.resources.textures,0);
  let old=gl.createFramebuffer();for(let n=0;n<10;n++){const next=gl.createFramebuffer();gl.deleteFramebuffer(old);old=next;}
  assert.equal(state.resources.framebuffers,1);
});
