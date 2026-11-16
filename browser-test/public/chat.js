// Browser presentation for the game's original console and chat send handler.
(() => {
  const panel = document.createElement('section');
  panel.id = 'browser-chat'; panel.hidden = true; panel.setAttribute('aria-label', 'Game chat');
  panel.innerHTML = '<button id="chat-toggle" type="button" aria-expanded="false">Chat</button><div id="chat-body" hidden><div id="chat-lines" role="log" aria-live="polite" aria-label="Game messages"></div><form id="chat-form"><input id="chat-input" aria-label="Chat message" maxlength="200" autocomplete="off" placeholder="Message · Enter to send"><button type="submit">Send</button></form><p id="chat-status" role="status"></p></div>';
  document.body.append(panel);
  const toggle = panel.querySelector('#chat-toggle'), body = panel.querySelector('#chat-body');
  const lines = panel.querySelector('#chat-lines'), input = panel.querySelector('#chat-input');
  const status = panel.querySelector('#chat-status');
  let lastSequence = 0, polling = false, sending = false;
  const history = [];
  function openChat(focus = true) {
    body.hidden = false; toggle.setAttribute('aria-expanded', 'true');
    if (focus) input.focus();
  }
  toggle.onclick = () => {
    if (body.hidden) openChat();
    else { body.hidden = true; toggle.setAttribute('aria-expanded', 'false'); document.querySelector('canvas')?.focus(); }
  };
  for (const type of ['keydown','keyup','keypress']) panel.addEventListener(type, e => e.stopPropagation());
  const form = panel.querySelector('#chat-form');
  const send = form.querySelector('button');
  // DirPlayer consumes document input defaults. Submit explicitly so its
  // canvas event handlers cannot cancel the browser form's default action.
  send.type = 'button';
  send.addEventListener('click', sendMessage);
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.preventDefault(); toggle.click(); }
    if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
  });
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
      const read = window.moonbaseRead, globals = read.globals();
      const sequence = Number(globals.browserConsoleVersion?.value || 0);
      if (sequence < lastSequence) { history.length = 0; lastSequence = 0; }
      if (sequence !== lastSequence) {
        const messages = read.list(globals.browserConsole);
        const count = messages.length;
        const amount = Math.min(sequence - lastSequence, count);
        for (let i = count - amount; i < count; i++) history.push(read.string(messages[i]));
        lastSequence = sequence;
        status.textContent = '';
        history.splice(0, Math.max(0, history.length - 100));
        lines.textContent = history.join('\n');
        lines.scrollTop = lines.scrollHeight;
      }
      // The original button toggles speech bubbles, whose text textures are
      // unsupported. Open the visible global console instead, retaining the
      // original Global Chat message path and validation.
      if (Number(globals.ChatBubbleMode?.value) === 1) {
        await evaluate('set ChatBubbleMode to 0');
        openChat();
        await evaluate('set member("ChatMode").text to "Global Chat"');
        status.textContent = 'Global chat · browser console';
      }
    } catch (error) {
      status.textContent = error.message;
    } finally { polling = false; }
  }, 500);
  form.addEventListener('submit', e => { e.preventDefault(); sendMessage(); });
  async function sendMessage() {
    const text = input.value.trim();
    if (!text || sending) return;
    sending = true;
    status.textContent = 'Submitting to game…';
    try {
      if (polling) throw new Error('Chat is updating; press Send again.');
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
            input.value = ''; status.textContent = 'Submitted to game'; return;
          }
        }
      } finally { window.__vm.key_up('Enter', 13); }
      status.textContent = 'The game did not clear this input. Check the connection before retrying.';
    } catch (error) { status.textContent = error.message; }
    finally { sending = false; }
  }
})();
