// Only accept controls from our embedding page. The original game's handlers
// receive the VM keys/clicks; this bridge does not replace gameplay or terms.
(() => {
  const bindings = {forward:['ArrowUp',38], back:['ArrowDown',40], left:['ArrowLeft',37], right:['ArrowRight',39],
    jetpack:['Control',17], dance:['Alt',18], brake:[' ',32], exit:['=',187]};
  const down = new Set();
  let lastHeartbeat = 0, enabled = false, activePointer = null;
  function snapshot() {
    const vm = window.__vm;
    if (!vm) return {loaded:false};
    const state = JSON.parse(vm.mcp_get_execution_state());
    const globals = state.movie_loaded ? window.moonbaseRead.globals() : {};
    return {loaded:state.movie_loaded, frame:state.current_frame, paused:state.is_paused,
      mode:window.moonbaseRead.string(globals.AvatarMode)};
  }
  function releaseAll() {
    for (const key of down) window.__vm?.key_up(...bindings[key]);
    down.clear();
  }
  function releasePointer() {
    if (activePointer) window.__vm?.mouse_up(...activePointer.point);
    activePointer = null;
  }
  function allowed(state, key) {
    return state.frame === 5 && !state.paused && (state.mode === 'Walking' ? !['brake','exit'].includes(key) :
      state.mode === 'Driving' && !['jetpack','dance'].includes(key));
  }
  function setKeys(keys) {
    const state = snapshot();
    const next = new Set(enabled && Array.isArray(keys) ? keys.filter(key => Object.hasOwn(bindings,key) && allowed(state,key)) : []);
    for (const key of down) if (!next.has(key)) { window.__vm?.key_up(...bindings[key]); down.delete(key); }
    for (const key of next) if (!down.has(key)) { window.__vm.key_down(...bindings[key]); down.add(key); }
    lastHeartbeat = Date.now();
  }
  const send = data => parent.postMessage(data, location.origin);
  const literal = text => Array.from(text, char => `numToChar(${char.codePointAt(0)})`).join(' & ') || 'empty';
  async function evaluate(source) {
    const result = JSON.parse(await window.__vm.mcp_eval_lingo(source));
    if (!result.success) throw new Error(result.error || 'Game input failed.');
    return result;
  }
  addEventListener('message', async event => {
    if (event.origin !== location.origin || event.source !== parent || event.data?.type !== 'moonbase-touch') return;
    const message = event.data;
    if (message.action === 'release') return releaseAll();
    if (message.action === 'enabled') { enabled = message.enabled === true; if (!enabled) releaseAll(); return; }
    if (message.action === 'keys') return setKeys(message.keys);
    try {
      const state = snapshot();
      if (!state.loaded || state.paused) throw new Error('Start the game inside the player first.');
      releaseAll();
      if (message.action === 'name') {
        if (state.frame !== 2) throw new Error('Choose your name on the login screen.');
        const name = String(message.text || '').trim().slice(0,20);
        if (!name) throw new Error('Enter a character name.');
        await evaluate(`set PlayerName to ${literal(name)}`);
        await evaluate(`set member("LoginName").text to ${literal(name)}`);
        send({type:'moonbase-touch-result', action:'name', ok:true, message:'Name set. Tap Login inside the game to continue.'});
      } else if (message.action === 'enter' && state.frame === 5 && state.mode === 'CharacterSetup') {
        // Authored 800 × 550 stage: route to the original Enter Base button,
        // including its own mode guard and console messages.
        const point = window.moonbaseCoordinates?.logicalToRender(665,80) || [665,80];
        window.__vm.mouse_move(...point); window.__vm.mouse_down(...point);
        setTimeout(() => window.__vm?.mouse_up(...point), 40);
      } else if (message.action === 'chat') {
        if (state.frame !== 5) throw new Error('Enter the world before chatting.');
        const result = await window.moonbaseChat.submit(String(message.text || '').slice(0,200));
        send({type:'moonbase-touch-result', action:'chat', ok:result.sent, message:result.message});
      }
    } catch (error) {
      send({type:'moonbase-touch-result', action:message.action, ok:false, message:error.message});
    }
  });
  document.addEventListener('moonbase-resolution-changing', () => { releaseAll(); releasePointer(); });
  for (const event of ['blur','pagehide','orientationchange']) addEventListener(event, () => { releaseAll(); releasePointer(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { releaseAll(); releasePointer(); } });
  setInterval(() => {
    if (down.size && Date.now() - lastHeartbeat > 1200) releaseAll();
    try {
      const state = snapshot();
      for (const key of down) if (!allowed(state,key)) { releaseAll(); break; }
      send({type:'moonbase-touch-state', ...state});
    } catch { releaseAll(); }
  }, 250);

  // DirPlayer's pointer handler subtracts the CSS-scaled outer rect but uses
  // its unscaled stage dimensions. Compensate using the actual canvas bounds.
  // Do not intercept the native Click to Play overlay or desktop text editing.
  const mount = document.getElementById('mount');
  function point(event) {
    const canvas = mount.querySelector('canvas');
    if (!canvas) return null;
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height || Math.abs(bounds.width - canvas.width) < 1) return null;
    if (!activePointer && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) return null;
    return [(event.clientX - bounds.left) * canvas.width / bounds.width, (event.clientY - bounds.top) * canvas.height / bounds.height];
  }
  mount.addEventListener('pointerdown', event => {
    if (!window.__vm || event.button !== 0 || event.target.closest('button,input,textarea,a')) return;
    const coords = point(event);
    if (!coords) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (activePointer) return;
    mount.setPointerCapture(event.pointerId);
    const vm = window.__vm;
    const sprite = vm.player_get_sprite_at?.(...coords) || 0;
    const editable = sprite > 0 && vm.is_sprite_editable_field?.(sprite);
    activePointer = {id:event.pointerId, point:coords, field:editable ? sprite : null};
    vm.mouse_move(...coords); vm.mouse_down(...coords);
    // We bypass React's unscaled pointer handler, so preserve its focus path:
    // the hidden native input forwards text/IME; the stage forwards game keys.
    if (editable) {
      mount.querySelector('input[type="text"]')?.focus({preventScroll:true});
      vm.field_set_caret_at?.(sprite, ...coords, !!event.shiftKey);
    } else {
      mount.querySelector('canvas')?.closest('[tabindex]')?.focus({preventScroll:true});
    }
  }, true);
  mount.addEventListener('pointermove', event => {
    if (activePointer && event.pointerId !== activePointer.id) return;
    const coords = point(event);
    if (!coords || !window.__vm) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (activePointer) activePointer.point = coords;
    window.__vm.mouse_move(...coords);
    if (activePointer?.field) window.__vm.field_drag_extend_to?.(activePointer.field, ...coords);
  }, true);
  for (const type of ['pointerup','pointercancel','lostpointercapture']) mount.addEventListener(type, event => {
    if (!activePointer || event.pointerId !== activePointer.id) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const coords = point(event) || activePointer.point;
    activePointer = null; window.__vm?.mouse_up(...coords);
  }, true);
})();
