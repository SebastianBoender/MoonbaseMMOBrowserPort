// Browser presentation for the game's original console and chat send handler.
(() => {
  const panel = document.createElement('section');
  panel.id = 'browser-chat'; panel.hidden = true; panel.setAttribute('aria-label', 'Game chat');
  panel.innerHTML = '<div id="chat-lines" role="log" aria-live="polite" aria-label="Game messages"></div><form id="chat-form"><input id="chat-input" aria-label="Chat message" maxlength="200" autocomplete="off" spellcheck="false" placeholder="_"></form><p id="chat-status" role="status"></p>';
  document.body.append(panel);
  const lines = panel.querySelector('#chat-lines'), input = panel.querySelector('#chat-input');
  const status = panel.querySelector('#chat-status'), form = panel.querySelector('#chat-form');
  let lastSequence = 0, polling = false, sending = false;
  const history = [];
  window.moonbaseChat = {
    async submit(text) {
      if (sending) return {sent:false, message:'Chat is sending. Try again in a moment.'};
      input.value = text;
      await sendMessage();
      return {sent:input.value === '', message:status.textContent};
    }
  };
  function openChat() { input.focus(); }
  function returnToGame() {
    input.blur();
    document.querySelector('canvas')?.closest('[tabindex]')?.focus();
  }
  for (const type of ['keydown','keyup','keypress']) panel.addEventListener(type, e => e.stopPropagation());
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.preventDefault(); returnToGame(); }
    if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
  });
  // Like the original, begin typing directly over the world. Movement and
  // modifier keys remain with the game until the player starts a message.
  addEventListener('keydown', e => {
    if (panel.hidden || panel.contains(e.target) || e.ctrlKey || e.altKey || e.metaKey || e.isComposing) return;
    // The original +/= shortcut leaves the vehicle. Let the game's keyDown
    // handler receive it rather than turning it into the start of a message.
    if ((e.key === '+' || e.key === '=') && window.__vm &&
        window.moonbaseRead.string(window.moonbaseRead.globals().AvatarMode) === 'Driving') return;
    if (e.key === 'Enter' || (e.key.length === 1 && e.key !== ' ')) {
      e.preventDefault(); e.stopPropagation(); openChat();
      if (e.key.length === 1 && input.value.length < input.maxLength) input.value += e.key;
    }
  }, true);
  function colorValue(datum) {
    const value = datum?.value || '';
    const hex = value.match(/#?([0-9a-f]{6})(?![0-9a-f])/i);
    if (hex) return `#${hex[1]}`;
    const rgb = value.match(/(?:rgb|color)\D+(\d+)\D+(\d+)\D+(\d+)/i);
    return rgb ? `rgb(${rgb.slice(1,4).map(Number).join(',')})` : '#fff';
  }
  function renderHistory() {
    const fragment = document.createDocumentFragment();
    for (const message of history.slice(-8)) {
      const line = document.createElement('div'); line.textContent = message.text || '\u00a0';
      line.style.color = message.color; fragment.append(line);
    }
    lines.replaceChildren(fragment);
  }
  function placeConsole() {
    const camera = window.moonbaseGPU?.camera, canvas = camera?.canvas;
    if (!canvas || !camera.viewport) return;
    const bounds = canvas.getBoundingClientRect(), [left, bottom, width, height] = camera.viewport;
    const scale = bounds.width / canvas.width;
    // Director's ConsoleH = sprite(1).width / 2 - 241. Eight 16px lines
    // sit above the original input line at stage height - 22.
    panel.style.left = `${bounds.left + (left + Math.max(0, width / 2 - 241)) * scale}px`;
    panel.style.top = `${bounds.top + (bottom + height - 150) * bounds.height / canvas.height}px`;
    panel.style.width = `${Math.min(482, width)}px`;
    panel.style.transform = `scale(${scale},${bounds.height / canvas.height})`;
  }
  async function evaluate(source) {
    const result = JSON.parse(await window.__vm.mcp_eval_lingo(source));
    if (!result.success) throw new Error(result.error || 'Game expression failed');
    return result;
  }
  setInterval(async () => {
    if (polling || sending || !window.__vm) return;
    polling = true;
    try {
      const vm = window.__vm;
      const state = JSON.parse(vm.mcp_get_execution_state());
      const active = state.movie_loaded && state.current_frame === 5 && new URLSearchParams(location.search).get('terrain') !== '0';
      panel.hidden = !active;
      if (!active || state.is_paused) return;
      placeConsole();
      const read = window.moonbaseRead, globals = read.globals();
      const sequence = Number(globals.browserConsoleVersion?.value || 0);
      if (sequence < lastSequence) { history.length = 0; lastSequence = 0; }
      if (sequence !== lastSequence) {
        const messages = read.list(globals.browserConsole);
        const count = messages.length;
        const amount = Math.min(sequence - lastSequence, count);
        for (let i = count - amount; i < count; i++) {
          const entry = read.list(messages[i]);
          history.push(entry.length ? {text:read.string(entry[0]), color:colorValue(entry[1])} : {text:read.string(messages[i]), color:'#fff'});
        }
        lastSequence = sequence;
        status.textContent = '';
        history.splice(0, Math.max(0, history.length - 100));
        renderHistory();
      }
      // The original button toggles speech bubbles, whose text textures are
      // unsupported. Open the visible global console instead, retaining the
      // original Global Chat message path and validation.
      if (Number(globals.ChatBubbleMode?.value) === 1) {
        await evaluate('set ChatBubbleMode to 0');
        openChat();
        await evaluate('set member("ChatMode").text to "Global Chat"');
        status.textContent = '';
      }
    } catch (error) {
      status.textContent = error.message;
    } finally { polling = false; }
  }, 500);
  form.addEventListener('submit', e => { e.preventDefault(); sendMessage(); });
  async function sendMessage() {
    const text = input.value.trim();
    if (sending) return;
    if (!text) { returnToGame(); return; }
    sending = true;
    status.textContent = '';
    try {
      if (polling) throw new Error('Chat is updating; press Enter again.');
      if (text !== '/fps') {
        const globals = window.moonbaseRead.globals();
        const accepted = window.moonbaseRead.string(globals.TermsOfUse) === 'Accepted';
        if (!accepted) throw new Error('Accept the original game terms on login before chatting.');
        if (Number(globals.OnlineConnection?.value) !== 1) throw new Error('Join a room before sending chat.');
      }
      // Numeric character expressions avoid interpolating message text as code.
      const expression = Array.from(text, char => `numToChar(${char.codePointAt(0)})`).join(' & ');
      await evaluate(`set browserGameplay.TextInput to ${expression}`);
      // Chat belongs to the 3D sprite's behavior, not a movie-level script.
      await evaluate('set the keyboardFocusSprite to 1');
      // This API takes browser keys/codes and maps them to Director codes.
      window.__vm.key_down('Enter', 13);
      // Let the original keyDown handler perform formatting, commands,
      // encryption and sendNetMessage. Never manufacture a server response.
      try {
        for (let attempt = 0; attempt < 40; attempt++) {
          await new Promise(resolve => setTimeout(resolve, 25));
          const game = window.moonbaseRead.inspect(window.moonbaseRead.globals().browserGameplay);
          if (window.moonbaseRead.string(game.properties?.TextInput) === '') {
            input.value = ''; status.textContent = ''; returnToGame(); return;
          }
        }
      } finally { window.__vm.key_up('Enter', 13); }
      status.textContent = 'The game did not clear this input. Check the connection before retrying.';
    } catch (error) { status.textContent = error.message; }
    finally { sending = false; }
  }
})();
