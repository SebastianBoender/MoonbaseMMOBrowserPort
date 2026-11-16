// Native controls outside the scaled Director canvas: Pointer Events support
// multiple held fingers without requiring a phone's keyboard for movement.
(() => {
  const get = id => document.getElementById(id);
  const game = get('game'), panel = get('touch-controls'), toggle = get('touch-toggle');
  const keys = [...panel.querySelectorAll('[data-game-key]')];
  const held = new Map();
  let state = {}, userPreference = false, namePending = false, chatPending = false;
  function post(data) {
    if (!game.hidden) game.contentWindow?.postMessage({type:'moonbase-touch', ...data}, location.origin);
  }
  function sync() { post({action:'keys', keys:[...new Set(held.values())]}); }
  function releaseAll() {
    held.clear(); keys.forEach(button => button.classList.remove('held'));
    post({action:'release'});
  }
  function release(pointerId) {
    const key = held.get(pointerId); held.delete(pointerId);
    if (![...held.values()].includes(key)) keys.find(button => button.dataset.gameKey === key)?.classList.remove('held');
    sync();
  }
  for (const button of keys) {
    button.addEventListener('pointerdown', event => {
      if (button.disabled || event.button !== 0) return;
      event.preventDefault();
      button.setPointerCapture(event.pointerId);
      held.set(event.pointerId, button.dataset.gameKey); button.classList.add('held'); sync();
    });
    for (const type of ['pointerup','pointercancel','lostpointercapture']) button.addEventListener(type, event => release(event.pointerId));
    button.addEventListener('contextmenu', event => event.preventDefault());
    // Keyboard accessibility for users who enable this panel on desktop.
    button.addEventListener('keydown', event => {
      if (button.disabled || ![' ','Enter'].includes(event.key)) return;
      event.preventDefault(); held.set(`keyboard-${button.dataset.gameKey}`, button.dataset.gameKey); button.classList.add('held'); sync();
    });
    button.addEventListener('keyup', event => {
      if ([' ','Enter'].includes(event.key)) { event.preventDefault(); release(`keyboard-${button.dataset.gameKey}`); }
    });
    button.addEventListener('blur', () => release(`keyboard-${button.dataset.gameKey}`));
  }
  const mobile = matchMedia('(any-pointer: coarse), (max-width: 760px)');
  function visible() {
    panel.hidden = !toggle.checked;
    if (panel.hidden) releaseAll();
    post({action:'enabled', enabled:toggle.checked});
  }
  function auto() { if (!userPreference) { toggle.checked = mobile.matches; visible(); } }
  mobile.addEventListener('change', auto); auto();
  toggle.addEventListener('change', () => { userPreference = true; visible(); });
  for (const event of ['blur','pagehide','orientationchange']) addEventListener(event, releaseAll);
  document.addEventListener('fullscreenchange', releaseAll);
  document.addEventListener('moonbase-fullscreenchange', releaseAll);
  document.addEventListener('visibilitychange', () => { if (document.hidden) releaseAll(); });
  panel.addEventListener('focusin', event => { if (event.target.matches('input')) releaseAll(); });
  // Heartbeats keep held keys alive; the iframe releases them if this parent
  // stops sending, is replaced, or disappears. Never re-press after a blur.
  setInterval(() => { if (held.size) sync(); }, 200);
  game.addEventListener('load', () => {
    releaseAll(); state = {}; namePending = chatPending = false;
    get('touch-name-form').querySelector('button').disabled = false; get('touch-send').disabled = false;
    get('touch-chat-form').hidden = true; get('touch-chat-status').textContent = ''; visible();
  });
  addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== game.contentWindow) return;
    const message = event.data;
    if (message?.type === 'moonbase-touch-state') {
      state = message;
      const walking = state.mode === 'Walking', driving = state.mode === 'Driving';
      const ready = state.frame === 5 && !state.paused;
      for (const button of keys) {
        const key = button.dataset.gameKey;
        button.disabled = !(ready && ((walking && !['brake','exit'].includes(key)) || (driving && !['jetpack','dance'].includes(key))));
      }
      if (!ready || (!walking && !driving)) releaseAll();
      get('touch-name-form').hidden = state.frame !== 2;
      get('touch-enter').hidden = !(ready && state.mode === 'CharacterSetup');
      get('touch-chat-toggle').disabled = !ready;
      get('touch-status').textContent = state.paused ? 'Game paused. Resume inside the player.' :
        !state.loaded ? 'Launch the game, then tap Play inside the player.' :
        state.frame === 2 ? 'Choose a name below, then tap Login in the game.' :
        state.frame !== 5 ? 'Continue inside the player. You can tap the original buttons.' :
        walking ? 'Walking · hold an arrow to move, or Jetpack to fly.' : driving ? 'Driving · arrows steer, Brake slows down, Exit car returns to walking.' : 'Tap Enter Base to start exploring.';
    } else if (message?.type === 'moonbase-touch-result') {
      if (message.action === 'name') { namePending = false; get('touch-name-form').querySelector('button').disabled = false; get('touch-status').textContent = message.message; }
      if (message.action === 'chat') {
        chatPending = false; get('touch-send').disabled = false;
        if (message.ok) { get('touch-chat').value = ''; get('touch-chat-form').hidden = true; }
        get('touch-chat-status').textContent = message.message;
      }
    }
  });
  get('touch-enter').addEventListener('click', () => { releaseAll(); post({action:'enter'}); });
  get('touch-name-form').addEventListener('submit', event => {
    event.preventDefault(); if (namePending) return;
    namePending = true; get('touch-name-form').querySelector('button').disabled = true;
    releaseAll(); post({action:'name', text:get('touch-name').value});
  });
  get('touch-chat-toggle').addEventListener('click', () => {
    releaseAll(); get('touch-chat-form').hidden = false; get('touch-chat').focus();
  });
  get('touch-chat-close').addEventListener('click', () => { get('touch-chat-form').hidden = true; get('touch-chat').blur(); releaseAll(); });
  get('touch-chat-form').addEventListener('submit', event => {
    event.preventDefault(); if (chatPending) return;
    chatPending = true; get('touch-send').disabled = true; releaseAll(); post({action:'chat', text:get('touch-chat').value});
  });
})();
