const $ = (id) => document.getElementById(id);
const events = [];
let pending = [];
let testOnLoad = false;
function addEvent(event) {
  const row = { ...event, time: event.time || new Date().toISOString() };
  events.push(row);
  if (events.length > 1000) events.shift();
  pending.push(row);
  if (pending.length > 100) pending.shift();
  $('count').textContent = `${events.length} events`;
  $('log').textContent = events.slice(-180).map(e => `${e.time.slice(11, 23)} [${e.level}] ${e.message}`).join('\n');
  $('log').scrollTop = $('log').scrollHeight;
  if (row.level === 'error') $('status').textContent = 'Player reported an error · see diagnostics';
  if (row.message.startsWith('Movie loaded')) $('status').textContent = 'Movie loaded · check the player';
  if (row.message.startsWith('Frame ')) $('status').textContent = `Movie running · ${row.message.toLowerCase()}`;
  if (row.message.startsWith('Multiplayer joined room ')) $('status').textContent = row.message;
  if (row.message.startsWith('3D startup complete;')) $('status').textContent = '3D setup verified · paused for offline inspection';
}
async function flush() {
  if (!pending.length) return;
  // The local collector accepts at most 64 KiB per request. Decompiled
  // handlers can be long, so count encoded bytes instead of just events.
  const batch = [];
  let bytes = 32;
  while (pending.length && batch.length < 100) {
    const size = new TextEncoder().encode(JSON.stringify(pending[0])).length + 1;
    if (bytes + size > 48000) break;
    bytes += size;
    batch.push(pending.shift());
  }
  try {
    const response = await fetch('/api/diagnostics', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ events: batch }) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch { pending = batch.concat(pending).slice(-100); }
}
setInterval(flush, 1500);
window.addEventListener('message', (event) => {
  if (event.origin !== location.origin || event.source !== $('game').contentWindow || event.data?.type !== 'moonbase-diagnostic') return;
  addEvent(event.data.event);
  if (testOnLoad && event.data.event.message.startsWith('Movie loaded')) {
    const type = testOnLoad === 'world' ? 'moonbase-test-world' : 'moonbase-test-3d';
    testOnLoad = false;
    $('game').contentWindow.postMessage({type}, location.origin);
  }
});
function launch(offline = false) {
  testOnLoad = offline === true ? 'offline' : (offline === 'world' ? 'world' : false);
  const params = new URLSearchParams({ mode: $('mode').value, flash: $('flash').checked ? '1' : '0', legacy: $('legacy').checked ? '1' : '0', terrain: $('terrain').checked ? '1' : '0', session: Date.now() });
  $('placeholder').hidden = true;
  $('game').hidden = false;
  $('game').src = `/player.html?${params}`;
  $('reload').disabled = false;
  $('fullscreen').disabled = false;
  $('start').textContent = 'Relaunch game';
  $('status').textContent = 'Loading runtime · click Play inside the player';
  addEvent({ level: 'info', message: `Launching DirPlayer 0.8.1; mode=${$('mode').value}; Flash=${$('flash').checked}` });
}
$('start').addEventListener('click', launch);
$('reload').addEventListener('click', launch);
$('inspect').addEventListener('click', () => {
  if ($('game').hidden) return addEvent({level:'info',message:'Launch the player before inspecting the VM.'});
  $('game').contentWindow.postMessage({type:'moonbase-inspect'}, location.origin);
});
$('test3d').addEventListener('click', () => {
  launch(true);
  addEvent({level:'info',message:'Offline test: fresh player started. Click to Play; 3D setup will run automatically and pause before connecting.'});
});
$('traceworld').addEventListener('click', () => {
  launch('world');
  addEvent({level:'info',message:'World trace: click Play; startup will connect and pause if logout is called.'});
});
$('fullscreen').addEventListener('click', () => $('game').requestFullscreen().catch(error => addEvent({ level:'error', message:String(error) })));
$('download').addEventListener('click', async () => {
  const status = await fetch('/api/status').then(r => r.json()).catch(() => ({}));
  const blob = new Blob([JSON.stringify({ status, events }, null, 2)], { type: 'application/json' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `moonbase-diagnostics-${Date.now()}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});
$('clear').addEventListener('click', () => { events.length = 0; $('log').textContent = 'View cleared. Saved diagnostic files are retained.'; $('count').textContent = '0 events'; });

$('runlingo').addEventListener('click', () => {
  if ($('game').hidden) return;
  $('game').contentWindow.postMessage({type:'moonbase-lingo', source:$('lingo').value}, location.origin);
});
