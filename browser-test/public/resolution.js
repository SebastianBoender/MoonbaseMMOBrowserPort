// Shared, DOM-free geometry. Render pixels never become gameplay coordinates.
((root, factory) => {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.moonbaseResolution = api;
})(typeof window === 'undefined' ? globalThis : window, () => {
  const logical = {width:800,height:550};
  const presets = Object.fromEntries([
    ['original','Original',550],['720p','720p',720],['1080p','1080p',1080],
    ['1440p','1440p / QHD (2K)',1440],['4k','4K / UHD',2160]
  ].map(([id,label,height])=>[id,{id,label,height,width:Math.round(height*16/11)}]));
  function preset(id) { if (!Object.hasOwn(presets,id)) throw new Error('Unknown resolution.'); return presets[id]; }
  function supported(id, limits) {
    const p=preset(id); return p.width<=limits.texture && p.height<=limits.texture &&
      p.width<=limits.renderbuffer && p.height<=limits.renderbuffer &&
      p.width<=limits.viewport[0] && p.height<=limits.viewport[1];
  }
  function summary(samples) {
    const values=samples.filter(v=>Number.isFinite(v)&&v>0).slice(-240).sort((a,b)=>a-b);
    if (!values.length) return {samples:0};
    const percentile=p=>values[Math.min(values.length-1,Math.ceil(values.length*p)-1)];
    const mean=values.reduce((a,b)=>a+b,0)/values.length;
    return {samples:values.length,fps:1000/mean,median:percentile(.5),p95:percentile(.95),longFrames:values.filter(v=>v>50).length};
  }
  return {logical,presets,preset,supported,summary};
});
