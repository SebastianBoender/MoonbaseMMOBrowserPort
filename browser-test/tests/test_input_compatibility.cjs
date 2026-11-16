const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../public/input-compatibility.js'), 'utf8');
function environment() {
  class Element { matches() { return this.input === true; } closest() { return this.inMount ? this : null; } }
  const listeners = new Map(), docListeners = new Map(), pressed = new Set();
  const add = (map, type, fn) => map.set(type, [...(map.get(type) || []), fn]);
  const document = {hidden:false, pointerLockElement:null, addEventListener:(type, fn) => add(docListeners,type,fn)};
  const window = {__vm:{key_up:(_,code) => pressed.delete(code)}};
  runInNewContext(source, {window, document, Element, addEventListener:(type,fn) => add(listeners,type,fn)});
  const game = new Element(), input = new Element(); input.input = true;
  const fire = (type,event={},doc=false) => ( (doc ? docListeners : listeners).get(type) || []).forEach(fn => fn(event));
  const down = (key,code) => { pressed.add(code); fire('keydown',{key,keyCode:code,target:game}); };
  return {fire,down,pressed,game,input,document};
}
test('arrow released in chat does not remain pressed in the VM', () => {
  const e = environment(); e.down('ArrowUp',38);
  e.fire('keyup',{key:'ArrowUp',keyCode:38,target:e.input});
  assert.equal(e.pressed.size,0);
});
test('chat focus cancels held arrows and jetpack Ctrl before the user releases them', () => {
  const e = environment(); e.down('ArrowLeft',37); e.down('Control',17);
  e.fire('focusin',{target:e.input},true);
  assert.equal(e.pressed.size,0);
});
test('lost window focus, hidden document, and pointer lock exit release held movement', () => {
  for (const reason of ['blur','pagehide','visibilitychange','pointerlockchange']) {
    const e = environment(); e.down('ArrowRight',39); e.document.hidden = true;
    e.fire(reason,{},['visibilitychange','pointerlockchange'].includes(reason));
    assert.equal(e.pressed.size,0,reason);
  }
});
test('acquiring pointer lock and ordinary game focus preserve movement', () => {
  const e = environment(); e.down('ArrowUp',38);
  e.document.pointerLockElement = e.game;
  e.fire('pointerlockchange',{},true); e.fire('focusin',{target:e.game},true);
  assert.equal(e.pressed.has(38),true);
});

test('the runtime hidden input still counts as game input for cleanup', () => {
  const e = environment(); e.game.input = true; e.game.inMount = true;
  e.down('Control',17); e.fire('blur');
  assert.equal(e.pressed.size,0);
});
