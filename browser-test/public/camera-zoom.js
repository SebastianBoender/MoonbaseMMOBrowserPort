// Widen only the 3D projection. Keep the authored camera, physics and 2D UI.
(() => {
  let scale = 1;
  const MIN = 0.5, MAX = 1;
  window.moonbaseZoom = {
    get scale() { return scale; },
    projection(matrix) {
      if (scale === MAX) return matrix;
      const result = new Float32Array(matrix);
      result[0] *= scale;
      result[5] *= scale;
      return result;
    }
  };
  document.getElementById('mount').addEventListener('wheel', event => {
    // Preserve browser pinch/zoom and scrolling in text/chat fields.
    if (event.ctrlKey || event.metaKey || event.target.closest('input,textarea,select,button,a,[contenteditable="true"],#browser-chat')) return;
    if (!event.target.closest('canvas') || !Number.isFinite(event.deltaY) || !event.deltaY) return;
    // Camera is meaningful only after entering the world. Never swallow the
    // wheel on the login, loader or a paused diagnostic screen.
    const vm = window.__vm;
    if (!vm) return;
    try {
      const state = JSON.parse(vm.mcp_get_execution_state());
      if (!state.movie_loaded || state.current_frame !== 5 || state.is_paused) return;
    } catch { return; }
    event.preventDefault();
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1);
    scale = Math.max(MIN, Math.min(MAX, scale * Math.exp(-Math.max(-400, Math.min(400, pixels)) * 0.0015)));
  }, {passive:false});
})();
