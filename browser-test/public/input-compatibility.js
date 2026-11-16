// Browser focus changes can deliver keyUp to chat, another frame, or no page.
// Keep the Director keyboard state in sync across those transitions.
(() => {
  const held = new Map();
  function release(key, code) { window.__vm?.key_up(key, code); }
  function releaseAll() {
    for (const [code, key] of held) release(key, code);
    held.clear();
  }
  function editing(target) {
    // DirPlayer's hidden input lives in #mount and forwards game keys to the
    // VM. Track it too; only browser UI editing (such as chat) takes focus away.
    return target instanceof Element && !target.closest('#mount') &&
      (target.matches('input,textarea,select') || target.isContentEditable);
  }
  addEventListener('keydown', event => {
    if (!editing(event.target) && !event.defaultPrevented) held.set(event.keyCode, event.key);
  }, true);
  // Capture runs before chat's stopPropagation, so a key pressed in the game
  // is released even when its keyUp lands in the text input.
  addEventListener('keyup', event => {
    if (!held.has(event.keyCode)) return;
    release(held.get(event.keyCode), event.keyCode);
    held.delete(event.keyCode);
  }, true);
  document.addEventListener('focusin', event => { if (editing(event.target)) releaseAll(); });
  document.addEventListener('moonbase-resolution-changing', releaseAll);
  addEventListener('blur', releaseAll);
  addEventListener('pagehide', releaseAll);
  document.addEventListener('visibilitychange', () => { if (document.hidden) releaseAll(); });
  document.addEventListener('pointerlockchange', () => { if (!document.pointerLockElement) releaseAll(); });
})();

// Escape also exits the in-page fullscreen fallback when the iframe has focus.
addEventListener('keydown', event => {
  if (event.key === 'Escape') parent.postMessage({type:'moonbase-exit-fullscreen'}, location.origin);
});
