(() => {
  const get=id=>document.getElementById(id), game=get('game');
  const modern=new URLSearchParams(location.search).get('client')==='modern';
  const selectors=[get('resolution'),get('fullscreen-resolution')];
  let desired='original';
  try { desired=localStorage.getItem('moonbase-modern-resolution')||'original'; } catch {}
  if (!Object.hasOwn(moonbaseResolution.presets,desired)) desired='original';
  window.moonbaseGraphics={client:modern?'modern':'original',resolution:modern?desired:'original',diagnostics:null};
  document.documentElement.dataset.client=modern?'modern':'original';
  get('modern-settings').hidden=!modern; get('fullscreen-quality').hidden=!modern;
  get('modern-client').setAttribute('aria-current',modern?'page':'false');
  get('original-client').setAttribute('aria-current',modern?'false':'page');
  if(modern){get('page-title').textContent='Moon Base · Modern';get('client-note').textContent='The original world, with optional higher-resolution rendering. Original quality is fastest.';}
  for(const selector of selectors){
    for(const p of Object.values(moonbaseResolution.presets)){const option=document.createElement('option');option.value=p.id;option.textContent=p.label;selector.append(option);}
    selector.value=desired;
    selector.addEventListener('change',()=>{
      desired=selector.value;for(const other of selectors)other.value=desired;
      window.moonbaseGraphics.resolution=desired;
      try{localStorage.setItem('moonbase-modern-resolution',desired);}catch{}
      if(!game.hidden)game.contentWindow?.postMessage({type:'moonbase-resolution',resolution:desired},location.origin);
    });
  }
  get('test-graphics-recovery').hidden=!modern;
  get('test-graphics-recovery').addEventListener('click',()=>game.contentWindow?.postMessage({type:'moonbase-render-test-loss'},location.origin));
  get('render-recover').addEventListener('click',()=>{get('resolution').value='original';get('resolution').dispatchEvent(new Event('change'));});
  addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==game.contentWindow||event.data?.type!=='moonbase-render-state')return;
    const state=event.data;
    const session=new URL(game.src,location.href).searchParams.get('session');
    if(state.session!==session)return;
    window.moonbaseGraphics.diagnostics=state;
    if(!state.busy){window.moonbaseGraphics.resolution=state.requested;desired=state.requested;}
    if(get('render-details'))get('render-details').textContent=JSON.stringify(state,null,2);
    if(state.client!=='modern')return;
    for(const selector of selectors){selector.disabled=!!state.busy;selector.value=state.requested;}
    if(state.limits)for(const selector of selectors)for(const option of selector.options)option.disabled=!moonbaseResolution.supported(option.value,state.limits);
    get('render-status').textContent=state.message + (state.scene?` · 3D scene ${state.scene.width} × ${state.scene.height}`:' · 3D scene starts in the world');
    if(state.slow)get('render-status').textContent+=' · Rendering is slow on this device. Try Original quality.';
    const m=state.metrics||{};
    get('render-metrics').textContent=m.samples?`3D draw cadence: ${m.fps.toFixed(0)} fps · median ${m.median.toFixed(1)} ms · p95 ${m.p95.toFixed(1)} ms · ${m.longFrames} frames >50 ms`:'3D performance appears after entering the world.';
    get('render-recover').hidden=!(state.slow||state.error);
    get('fullscreen-render-status').textContent=state.busy?'Applying…':`${state.width} × ${state.height}`;
  });
})();
