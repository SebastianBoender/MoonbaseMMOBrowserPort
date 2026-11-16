// Present the game's existing projected camera nameplates as browser text.
(() => {
  const layer = document.createElement('div');
  layer.id = 'player-labels'; layer.setAttribute('aria-label', 'Player names');
  document.body.append(layer);
  const labels = new Map();
  setInterval(() => {
    if (!window.__vm) return;
    const state = JSON.parse(window.__vm.mcp_get_execution_state());
    layer.hidden = !state.movie_loaded || state.current_frame !== 5 || new URLSearchParams(location.search).get('terrain') === '0';
    if (layer.hidden || state.is_paused) return;
    const camera = window.moonbaseGPU?.camera, canvas = camera?.canvas;
    if (!canvas || !camera.viewport) return;
    const read = window.moonbaseRead, globals = read.globals();
    const width = Number(globals.ScreenH?.value), height = Number(globals.ScreenV?.value);
    if (!(width > 0 && height > 0)) return;
    const bounds = canvas.getBoundingClientRect();
    Object.assign(layer.style, {left:`${bounds.left}px`, top:`${bounds.top}px`, width:`${bounds.width}px`, height:`${bounds.height}px`});
    const seen = new Set();
    for (const datum of read.list(globals.browserLabels)) {
      const [source, point] = read.list(datum);
      if (source?.type_name !== 'string') continue;
      const name = read.string(source), key = name;
      const coordinates = point?.value.match(/-?\d+(?:\.\d+)?/g)?.map(Number);
      if (!name || !coordinates || coordinates.length !== 3) continue;
      const multiply = (matrix, vector) => [0,1,2,3].map(row => vector.reduce((sum, v, col) => sum + matrix[col * 4 + row] * v, 0));
      const clip = multiply(camera.projection, multiply(camera.view, [...coordinates, 1]));
      if (!(clip[3] > 0) || clip[2] < -clip[3] || clip[2] > clip[3]) continue;
      const [left, bottom, vw, vh] = camera.viewport;
      const x = left + (clip[0] / clip[3] + 1) * vw / 2;
      // DirPlayer flips projection Y for its offscreen 3D texture; the stage
      // compositor then displays that texture with a second Y flip.
      const y = bottom + (clip[1] / clip[3] + 1) * vh / 2 - 16;
      if (x < left || x > left + vw || y < bottom || y > bottom + vh) continue;
      let element = labels.get(key);
      if (!element) { element = document.createElement('span'); labels.set(key, element); layer.append(element); }
      element.textContent = name;
      element.style.left = `${x / canvas.width * 100}%`; element.style.top = `${y / canvas.height * 100}%`;
      seen.add(key);
    }
    for (const [key, element] of labels) if (!seen.has(key)) { element.remove(); labels.delete(key); }
  }, 100);
})();
