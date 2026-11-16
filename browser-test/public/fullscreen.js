// Keep the original stage and native touch controls together. On browsers
// without element fullscreen (including some phones), expand within the page.
(() => {
  const surface = document.getElementById('play-surface');
  const enter = document.getElementById('fullscreen');
  const exit = document.getElementById('exit-fullscreen');
  const touch = document.getElementById('fullscreen-touch');
  const toggle = document.getElementById('touch-toggle');
  let fallback = false, previousFocus = null;
  const nativeElement = () => document.fullscreenElement || document.webkitFullscreenElement;
  function update() {
    const active = fallback || nativeElement() === surface;
    surface.classList.toggle('is-fullscreen', active);
    document.documentElement.classList.toggle('game-fullscreen', active);
    enter.setAttribute('aria-pressed', String(active));
    touch.setAttribute('aria-pressed', String(toggle.checked));
    document.dispatchEvent(new Event('moonbase-fullscreenchange'));
    if (!active && previousFocus) { previousFocus.focus({preventScroll:true}); previousFocus = null; }
  }
  async function open() {
    if (fallback || nativeElement() === surface) return;
    previousFocus = document.activeElement;
    const request = surface.requestFullscreen || surface.webkitRequestFullscreen;
    try {
      if (!request) throw new Error('Use in-page fullscreen');
      await request.call(surface);
    } catch { fallback = true; }
    update();
  }
  async function close() {
    if (fallback) { fallback = false; update(); return; }
    if (nativeElement() === surface) {
      try { await (document.exitFullscreen || document.webkitExitFullscreen).call(document); }
      catch { return; }
      update();
    }
  }
  enter.addEventListener('click', open);
  exit.addEventListener('click', close);
  touch.addEventListener('click', () => { toggle.click(); update(); });
  toggle.addEventListener('change', update);
  document.addEventListener('fullscreenchange', update);
  document.addEventListener('webkitfullscreenchange', update);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && fallback) close(); });
  addEventListener('message', event => {
    if (event.origin === location.origin && event.source === document.getElementById('game').contentWindow && event.data?.type === 'moonbase-exit-fullscreen' && fallback) close();
  });
  update();
})();
