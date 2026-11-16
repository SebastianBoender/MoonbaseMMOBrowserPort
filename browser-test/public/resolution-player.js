(() => {
  const params=new URLSearchParams(location.search), modern=params.get('client')==='modern';
  const config=window.moonbaseResolution;
  let selected='original', requested='original', busy=false, loaded=false, error=false, message='Original rendering · 800 × 550';
  let generation=0, lastCanvas=null, limits=null;
  let initial=Object.hasOwn(config.presets,params.get('resolution'))?params.get('resolution'):'original';
  if(modern)requested=initial;
  const target=()=>config.preset(selected);
  const send=()=>{
    const gpu=window.moonbaseGPU, p=target(), metrics=config.summary(gpu?.frameTimes||[]);
    const slow=metrics.samples>=60&&metrics.median>40&&selected!=='original';
    parent.postMessage({type:'moonbase-render-state',session:params.get('session'),client:modern?'modern':'original',selected,requested,busy,error,message,
      width:p.width,height:p.height,scene:gpu?.camera?{width:gpu.camera.viewport[2],height:gpu.camera.viewport[3]}:null,
      metrics,slow,resources:gpu?.resources||null,limits},location.origin);
  };
  function resetMetrics(){ window.moonbaseGPU?.resetTimings?.(); }
  function capabilities(canvas){
    const gl=canvas.getContext('webgl2');
    if(!gl||gl.isContextLost())throw new Error('WebGL2 is unavailable. Use the Original client.');
    return {texture:gl.getParameter(gl.MAX_TEXTURE_SIZE),renderbuffer:gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),viewport:Array.from(gl.getParameter(gl.MAX_VIEWPORT_DIMS))};
  }
  function releaseInput(){ document.dispatchEvent(new Event('moonbase-resolution-changing')); }
  function attachCanvas(){
    const canvas=window.moonbaseCoordinates.canvas();
    if(!canvas||lastCanvas===canvas)return;
    lastCanvas=canvas;
    canvas.addEventListener('webglcontextlost',event=>{
      if(!modern)return;
      event.preventDefault();generation++;busy=false;error=true;releaseInput();
      message='Graphics context lost. Waiting to restore Original quality…';send();
    });
    canvas.addEventListener('webglcontextrestored',()=>{
      if(!modern)return;
      try{
        window.__vm.set_renderer_backend('webgl2');lastCanvas=null;limits=null;
        if(window.moonbaseGPU)window.moonbaseGPU.resources={framebuffers:0,renderbuffers:0,textures:0};
        selected=requested='original';
        apply('original','Graphics restored at Original quality.');
      }catch{message='Graphics could not be restored. Relaunch the game to recover.';error=true;send();}
    });
  }
  async function resize(id, token){
    const p=config.preset(id), vm=window.__vm, canvas=window.moonbaseCoordinates.canvas();
    limits=capabilities(canvas);
    if(!config.supported(id,limits))throw new Error(`${p.label} exceeds this device’s graphics limits.`);
    vm.set_stage_size(p.width,p.height);
    const started=performance.now();
    while(performance.now()-started<3000){
      if(token!==generation)return false;
      const current=window.moonbaseCoordinates.canvas();
      if(current?.width===p.width&&current?.height===p.height)return true;
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    throw new Error('The renderer did not accept the new resolution.');
  }
  async function apply(id, recoveryMessage=''){
    if(!modern||!loaded||busy)return;
    try{config.preset(id);}catch{return;}
    const previous=selected, token=++generation;
    requested=id;busy=true;error=false;releaseInput();message=`Applying ${config.preset(id).label}…`;send();
    try{
      if(!await resize(id,token))return;
      // Observe a draw before accepting: allocation errors arrive via the
      // renderer's diagnostics. Native changes never restart the movie/socket.
      await new Promise(resolve=>setTimeout(resolve,300));
      if(token!==generation)return;
      selected=id;resetMetrics();
      const p=target();message=recoveryMessage||`${p.label} · ${p.width} × ${p.height} render pixels · original camera and layout`;
    }catch(failure){
      if(token!==generation)return;
      requested=previous;error=true;
      try{await resize(previous,token);selected=previous;message=`${failure.message} Restored ${config.preset(previous).label}.`;}
      catch{message='Resolution recovery failed. Relaunch with Original quality.';}
    }finally{if(token===generation){busy=false;send();}}
  }
  addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==parent)return;
    if(event.data?.type==='moonbase-render-test-loss'&&modern&&loaded&&!busy){
      const extension=window.moonbaseCoordinates.canvas()?.getContext('webgl2')?.getExtension('WEBGL_lose_context');
      if(extension){extension.loseContext();setTimeout(()=>extension.restoreContext(),700);}
      return;
    }
    if(event.data?.type!=='moonbase-resolution')return;
    const id=event.data.resolution;
    if(!Object.hasOwn(config.presets,id))return;
    if(!loaded){initial=id;requested=id;send();return;}
    apply(id);
  });
  addEventListener('moonbase-runtime',event=>{
    if(event.detail.kind!=='movie-loaded')return;
    loaded=true;attachCanvas();
    if(modern)setTimeout(()=>apply(initial),100);
  });
  addEventListener('moonbase-render-error',event=>{
    if(!modern||!loaded||!/\[3D\].*Render failed|incomplete 3D framebuffer/.test(String(event.detail)))return;
    const restore=busy?selected:'original';
    generation++;busy=false;requested=restore;error=true;
    releaseInput();
    window.__vm.set_stage_size(config.preset(restore).width,config.preset(restore).height);
    message=`The higher-resolution 3D target failed. Restored ${config.preset(restore).label}.`;send();
  });
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){releaseInput();}
    else{resetMetrics();}
  });
  setInterval(()=>{attachCanvas();if(!document.hidden)send();},1000);
  document.documentElement.dataset.client=modern?'modern':'original';
  send();
})();
