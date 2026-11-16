(() => {
  // Preserve the original 800 × 550 stage and fit the whole player to a
  // smaller iframe. Canvas pointer coordinates and overlays use its bounds.
  const fitStage = () => document.documentElement.style.setProperty('--game-scale',
    Math.min(document.documentElement.clientWidth / 800, document.documentElement.clientHeight / 550));
  new ResizeObserver(fitStage).observe(document.documentElement);
  fitStage();
  const params = new URLSearchParams(location.search);
  let sent = 0;
  const serialize = (value) => {
    if (value instanceof Error) return value.stack || value.message;
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value) ?? String(value); } catch { return String(value); }
  };
  const report = (level, message) => {
    if (++sent > 3000 && level !== 'error') return;
    parent.postMessage({ type: 'moonbase-diagnostic', event: {
      level, message: String(message).slice(0, 6000), time: new Date().toISOString(), session: params.get('session')
    } }, location.origin);
  };
  for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
    const original = console[level].bind(console);
    console[level] = (...values) => { original(...values); report(level, values.map(serialize).join(' ')); };
  }
  addEventListener('error', event => report('error', event.error?.stack || event.message || `Resource failed: ${event.target?.src || event.target?.href || 'unknown'}`), true);
  addEventListener('unhandledrejection', event => report('error', serialize(event.reason)));
  addEventListener('message', async event => {
    if (event.origin !== location.origin || event.source !== parent || !['moonbase-inspect','moonbase-test-3d','moonbase-test-world','moonbase-lingo'].includes(event.data?.type)) return;
    const vm = window.__vm;
    if (!vm) return report('warn', 'VM not initialized yet.');
    if (['moonbase-test-3d','moonbase-test-world'].includes(event.data.type)) {
      const world = event.data.type === 'moonbase-test-world';
      if (!JSON.parse(vm.mcp_get_execution_state()).movie_loaded) return report('warn', 'Click to Play and wait for the movie to load first.');
      const code = JSON.parse(vm.mcp_disassemble_handler(1,5,'beginSprite')).bytecode;
      const boundary = code.findIndex(op => op.opcode === 'ExtCall' && op.text.endsWith('extcall makeAServerConnection'));
      if (boundary < 0) return report('error', 'Cannot locate the offline inspection breakpoint.');
      const scriptName = world ? 'Connection Script' : 'SpriteBehavior';
      const handlerName = world ? 'logout' : 'beginSprite';
      const breakIndex = world ? 0 : boundary;
      vm.add_breakpoint(scriptName, handlerName, breakIndex);
      report('info', world ? 'World trace: opening frame 5 and pausing on logout.' : 'Isolated test: opening frame 5; debugger will pause after physics setup, before the server connection.');
      let attempts = 0;
      const watch = setInterval(() => {
        const state = JSON.parse(vm.mcp_get_execution_state());
        if (world && attempts % 20 === 0) {
          const globals = JSON.parse(vm.mcp_get_globals()).globals;
          const values = Object.fromEntries(['OnlineConnection','RoomNumber','UsersRoom','UsersServer','OldTimeCheck'].map(k => [k,globals[k]?.value]));
          report('info', `World connection state: ${JSON.stringify(values)}`);
        }
        if (state.at_breakpoint || state.is_paused || ++attempts > (world ? 1200 : 100)) {
          clearInterval(watch);
          vm.remove_breakpoint(scriptName, handlerName, breakIndex);
          if (state.at_breakpoint) {
            report('info', world ? 'World trace paused on logout; inspect scope-list for the caller.' : '3D startup complete; debugger paused before multiplayer connection.');
            if (world) {
              const globals = JSON.parse(vm.mcp_get_globals()).globals;
              report('info', `World trace clock/network: ${JSON.stringify(Object.fromEntries(['OldTimeCheck','OnlineConnection','RoomNumber','SysTime'].map(k => [k,globals[k]])))}`);
              report('info', `World trace CheckTime locals: ${vm.mcp_get_locals(0)}`);
            }
          }
        }
      }, 100);
      report('info', await vm.mcp_eval_lingo('go to frame 5'));
      return;
    }
    if (event.data.type === 'moonbase-lingo') {
      if (String(event.data.source).trim() === '@physics') {
        for (const handler of ['DrivePlayer', 'CheckCarFlipped', 'prepareFrame']) report('info', `Physics handler ${handler}: ${vm.mcp_decompile_handler(1,5,handler)}`);
        // Observe live input and bodies while native keys remain on the game.
        // This trace never changes input, velocities, or server state.
        let samples = 0;
        const trace = setInterval(async () => {
          const values = {};
          for (const expression of ['the controlDown + 0', 'browserGameplay.FrameMod + 0', 'moongravity + 0', 'sp.modelResource("RocketPack").emitter.loop + 0', 'checkheight(havok.rigidBody("TheBall").position, 0)', ...['Walk', 'Car', 'Spring', 'TheBall'].flatMap(body => [`havok.rigidBody("${body}").position`, `havok.rigidBody("${body}").linearVelocity`])]) {
            try { values[expression] = JSON.parse(await vm.mcp_eval_lingo(expression)); }
            catch (error) { values[expression] = serialize(error); }
          }
          report('info', `Physics sample ${++samples}: ${JSON.stringify(values)}`);
          if (samples >= 40) clearInterval(trace);
        }, 500);
        return;
      }
      for (const source of String(event.data.source || '').split('\n').filter(s => s.trim())) {
        try { report('info', `Lingo ${source}: ${await vm.mcp_eval_lingo(source)}`); }
        catch (error) { report('warn', `Lingo ${source}: ${serialize(error)}`); }
      }
      return;
    }
    for (const [count, uniforms] of Object.entries(window.moonbaseGPU?.draws || {})) report('info', `GPU draw ${count}: ${JSON.stringify(uniforms)}`);

    for (const [lib, member, handlers] of [[1,23,['beginSprite','mouseUp']],[1,37,['beginSprite','mouseDown']],[1,49,['PrintToConsole','chatMessageHandler']]]) {
      for (const handler of handlers) report('info', `Chat handler ${lib}:${member}.${handler}: ${vm.mcp_decompile_handler(lib,member,handler)}`);
    }
    const scripts = JSON.parse(vm.mcp_list_scripts(-1, 100, 0)).scripts;
    report('info', `Gameplay script inventory: ${JSON.stringify(scripts.filter(s => s.cast_lib === 3))}`);
    for (const script of scripts.filter(s => /gravity|slider|knob|enterworld/i.test(s.name))) {
      for (const handler of script.handlers) {
        report('info', `Gameplay ${script.name}.${handler}: ${vm.mcp_decompile_handler(script.cast_lib,script.cast_member,handler)}`);
      }
    }
    for (const handler of ['beginSprite','mouseUp','keyDown','prepareFrame','SwitchAvatarMode','MoveCamera','CheckWindowRescale','WalkPlayer','FramerateTest','SetupPhysics','collisioncallbackwalk','MakeRocketPack']) {
      report('info', `Gameplay SpriteBehavior.${handler}: ${vm.mcp_decompile_handler(1,5,handler)}`);
    }
    for (const handler of ['makeTerrain','createrocks']) report('info', `World MakeTheTerrain.${handler}: ${vm.mcp_decompile_handler(1,8,handler)}`);
    for (const expression of ['sp.model("GroundShape").shaderList','sp.model("EarthShape").visibility','sp.model("StarsShape").visibility','sprite(2).visible','AvatarMode & empty','moongravity + 0','sprite(3).loc','sprite(3).rect','sprite(4).loc','sprite(4).rect','sprite(4).member.regPoint','sprite(4).member.rect','sprite(1).width','sprite(1).height','sp.model("CameraBox").worldPosition','havok.rigidBody("CameraBox").position','PlayerModel.worldPosition','PlayerSphere.worldPosition','FollowCamera.transform.position','FollowCamera.worldPosition','sp.model("CameraTargetPh").worldPosition','sp.model("WalkFrontTarget").worldPosition']) {
      report('info', `Gameplay value ${expression}: ${await vm.mcp_eval_lingo(expression)}`);
    }
    for (const [name, args] of [['mcp_get_execution_state',[]], ['mcp_get_context',[]],
      ['mcp_get_globals',[]], ['mcp_get_call_stack',[8,true]], ['mcp_list_scripts',[-1,100,0]],
      ['mcp_get_console_output',[40]], ['mcp_decompile_handler',[1,17,'prepareMovie']],
      ['mcp_decompile_handler',[1,17,'startMovie']], ['mcp_decompile_handler',[1,49,'CheckTime']],
      ['mcp_decompile_handler',[1,30,'exitFrame']], ['mcp_decompile_handler',[1,4,'exitFrame']]]) {
      try { report('info', `${name}${args.length ? `(${args.join(',')})` : ''}: ${vm[name](...args)}`); }
      catch (error) { report('warn', `${name}: ${serialize(error)}`); }
    }
  });
  addEventListener('securitypolicyviolation', event => {
    if (event.violatedDirective === 'object-src' && !event.blockedURI) return;
    report('warn', `Blocked external request: ${event.blockedURI} (${event.violatedDirective})`);
  });
  let frames = 0;
  let lastFrame = null;
  let connectionWatch = null;
  addEventListener('moonbase-runtime', event => {
    const { kind, value } = event.detail;
    if (kind === 'frame') {
      if (++frames <= 5 || value !== lastFrame || frames % 120 === 0) report('info', `Frame ${value}`);
      lastFrame = value;
      if (value === 5 && !connectionWatch) {
        let checks = 0;
        connectionWatch = setInterval(() => {
          try {
            const globals = JSON.parse(window.__vm.mcp_get_globals()).globals;
            if (globals.OnlineConnection?.value === '1') {
              report('info', `Multiplayer joined room ${globals.RoomNumber?.value || '?'}.`);
              clearInterval(connectionWatch);
            } else if (++checks > 60) clearInterval(connectionWatch);
          } catch (error) { report('warn', serialize(error)); clearInterval(connectionWatch); }
        }, 2000);
      }
      return;
    }
    if (kind === 'movie-loaded') report('info', `Renderer: ${window.__vm?.get_renderer_backend()}; WebGL2 supported: ${window.__vm?.is_webgl2_supported()}`);
    if (kind === 'scope-list' && (!value || value.length === 0)) return;
    report(kind === 'script-error' ? 'error' : 'info',
      `${kind === 'movie-loaded' ? 'Movie loaded' : kind}: ${serialize(value)}`);
  });
  window.alert = message => {
    report('warn', `Game alert: ${message}`);
    const notice = document.getElementById('notice'); notice.textContent = String(message); notice.hidden = false;
    notice.onclick = () => { notice.hidden = true; };
  };
  const script = document.createElement('script');
  const vmReady = setInterval(() => {
    if (!window.__vm) return;
    clearInterval(vmReady);

    if (params.get('legacy') === '1') {
      window.__vm.set_ir_enabled(false);
      report('info', 'Compatibility test: legacy bytecode interpreter selected.');
    }
  }, 50);
  script.src = '/vendor/dirplayer-0.8.1/dirplayer-diagnostic.js';
  script.setAttribute('data-manual-init', '');
  script.setAttribute('data-require-click', '');
  if (params.get('flash') === '0') script.setAttribute('data-disable-flash', '');
  script.onload = () => {
    window.DirPlayer.configureFlash({ logLevel: 'warn', disableFlash: params.get('flash') === '0' });
    // The local bridge forwards binary MUS to the fixed legacy TCP server.
    window.dirplayerResolveSocketUrl = (host, port) => {
      const url = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/mus`;
      report('warn', `Multiuser requested ${host}:${port}; redirected to ${url}. Forwarded to legacy TCP server pigyak.com:1626.`);
      return url;
    };
    window.DirPlayer.init();
    const object = document.createElement('object');
    object.type = 'application/x-director'; object.setAttribute('width', '800'); object.setAttribute('height', '550');
    const external = { src: params.get('terrain') === '0' ? '/game/moonbase.dir' : '/game/moonbase-browser.dir', _runMode: params.get('mode') === 'Projector' ? 'Projector' : 'Shockwave',
      _moviePath: 'http://www.maidmarian.com/Moonbase/', swStretchStyle: 'fill' };
    for (const [name, value] of Object.entries(external)) {
      const param = document.createElement('param'); param.name = name; param.value = value; object.appendChild(param);
    }
    document.getElementById('mount').appendChild(object);
    report('info', 'Runtime initialized; recovered movie mounted. Click to Play starts the original Lingo.');
  };
  script.onerror = () => report('error', 'DirPlayer bundle missing. Run python3 browser-test/setup.py.');
  document.head.appendChild(script);
})();
