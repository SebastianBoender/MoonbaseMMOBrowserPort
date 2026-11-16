# Moonbase / DirPlayer local test environment

From the original package directory, run:

```bash
python3 browser-test/run.py
```

Open **http://127.0.0.1:8080**, click **Launch game**, then **Click to Play** inside the player. The launcher verifies dependencies, prepares the recovered movie and starts a detached loopback-only server. Python 3.10+ is sufficient; no npm, Rust, Wine, Shockwave install or GPU server is needed. The first setup downloads the pinned official browser release if it is not already installed. After that the test runs from local assets.

Stop the managed server with:

```bash
python3 browser-test/run.py --stop
```

To run setup and a foreground server separately (Ctrl+C to stop):

```bash
python3 browser-test/setup.py
python3 browser-test/serve.py --port 8080
```

Use `--port 8081` on the launcher if 8080 is occupied; use the same port when stopping it. This is a local development host; production VPS configuration is a later step.

## Included

- DirPlayer **0.8.1**, downloaded from its official GitHub release. Its ZIP is verified against the published SHA-256 `6f5000412c50833345a630ade25fb70359dc4e1aae66352c80de7da77542162c`.
- The matching bundled Ruffle fork for the game's embedded Flash assets, and packaged WASM Xtras.
- A standalone `public/game/moonbase.dir`, extracted from this exact game EXE. The extractor relocates 215 resource-map entries and the index-map pointer. It preserves Lingo, graphics, score and other resource payloads, verifies relocated addresses, and writes `public/game/manifest.json` with provenance and payload hashes.
- A browser test page with restart/fullscreen, Shockwave/Projector mode selection, optional Flash disabling, and an experimental legacy-interpreter toggle under diagnostics. Change options and relaunch to apply them.
- An **Inspect VM** button that captures execution state, globals, stack, script inventory and selected decompiled startup handlers using DirPlayer's debugging API.
- Browser events saved locally in `logs/browser.jsonl`; HTTP server output in `logs/server.log`; downloadable session diagnostics from the page.

The original Windows binaries and scripts remain unchanged and are never executed by this environment. The default browser movie is a separate compatibility copy, described below; the faithful extracted baseline is retained. Only `public/` is served; EXEs, original VBS files and logs are outside the static document root.

## Runtime diagnostics adaptation

The original verified `vendor/dirplayer-0.8.1/dirplayer-polyfill.js` is retained intact. Setup creates `dirplayer-diagnostic.js` alongside it, adding observational CustomEvents at five VM callback entry points. These expose movie-loaded, frame, script-error, debug-message and stack notifications to the local page. `diagnostic-hooks.json` records both hashes and exact hook targets. This does not patch the interpreter or game logic. Rebuilding the diagnostics bundle is automatic during setup.

Upstream reports many original Xtra filenames as "missing" from the optional external WASM registry even when functionality is implemented internally. That list alone is not a fatal-error list. Actual script errors and observed behavior are more useful.

`_moviePath` is set to a legacy Maid Marian location **as a label only**, for compatibility with movies that inspect their path. It does not change the download location: the movie is loaded locally. Informational `alert()` calls become a dismissible on-page notice so a native modal does not hide the diagnostics.

## Legacy server test connection

Normal gameplay connects through same-origin `/mus`, a WebSocket-to-TCP bridge fixed to **pigyak.com:1626**, the destination embedded in this game. This was enabled at the user's request for original-server testing. The address resolved and accepted a TCP connection during setup; a real room join has since been verified with the callback adaptations below.

The bridge forwards the runtime's binary MUS protocol unchanged. Player names, game messages and any chat entered are sent to that remote service. The legacy TCP leg is unencrypted. No account passwords are required by this launcher. The local HTTP host remains bound to 127.0.0.1; the bridge checks the browser Origin, only accepts masked binary messages, and does not accept a destination from the client. Browser CSP still restricts connections to the local host.

`mus_bridge.py` implements this transport using Python's standard library. Run `python3 browser-test/tests/test_mus_bridge.py` to verify the WebSocket transport against a local echo server (no remote game login). A failed upstream connection returns HTTP 502 and logs the cause in `logs/server.log`. The bridge is not a replacement game backend and does not simulate successful login. **Test 3D startup** remains an offline inspection path that pauses before the connection call.

## Verification and current limits

The recovered movie has been loaded in the Codex in-app browser. The Maid Marian intro and original astronaut/MOONBASE login screen rendered, including the character-name field, Login button and Terms of Use link. The embed uses the recovered movie’s original 800 × 550 stage size. The VM reports a loaded, playing 35-frame movie. Startup to the title screen took several seconds. This verifies extraction, WASM startup and part of the original 2D timeline; the later compatibility test below also reaches 3D initialization. The later tests below also verify a real room join and camera transition; full multiplayer gameplay and physics fidelity remain unverified.

Default and legacy interpreter modes were exercised. The legacy toggle remains optional; the final verified login screen uses the default interpreter, and no interpreter-level fix is claimed. The faithful extracted baseline remains available by disabling **Browser compatibility fixes** and relaunching. Use **Inspect VM** and **Download diagnostics** when reporting an issue. Logs may include names or chat entered during future tests; they are local to this environment.

Upstream source and licensing:

- [DirPlayer source at v0.8.1](https://github.com/igorlira/dirplayer-rs/tree/v0.8.1)
- [Official release](https://github.com/igorlira/dirplayer-rs/releases/tag/v0.8.1)
- DirPlayer license: `public/vendor/dirplayer-0.8.1/LICENSE`; Ruffle license notices are in its `ruffle/` folder.

The browser runtime's licenses do not grant redistribution rights to the original Moonbase game assets.

## Browser compatibility fixes

The default `moonbase-browser.dir` is a reproducible adapter copy of the untouched `moonbase.dir`. `compatibility.py` makes the following targeted changes:

1. In `makeTerrain` and `checkheight`, five calls to `getPixel(image, x, y, #integer)` become the equivalent `getPixel(image, point(x, y), #integer)`. DirPlayer 0.8.1 honors the integer flag only for its point-coordinate form. Without this change terrain initialization produces a color value and fails at `thisHeight * hFactor - 2000` with `Invalid operands for subtract_datums: color_ref, int`.
2. The internal name-table entry `RigidBody` is spelled `rigidBody`, matching the runtime's Havok dispatcher. Director treats the names case-insensitively; the pinned emulator's dispatcher does not accept the original spelling. This resolves the next `No handler RigidBody for Havok member` error.

3. `CheckTime` reads `the milliSeconds` instead of the seconds-resolution `the abbr time`. A debugger breakpoint confirmed the original check called `logout()` during world startup when the clock string repeated. The timer and logout logic remain in place; the timestamp now has the precision needed for queued browser callbacks.
4. DirPlayer only retains one `setNetMessageHandler` callback, ignoring subject filters and automatic message-argument delivery. The adapter routes all registrations through `DefaultMessageHandler`, which reads the actual `getNetMessage()` queue and passes each message to the original matching game handler. This restores room joins, positions and other registered message routes. The package references a `DailyMessageHandler` that it does not implement; that absent handler is not fabricated.

5. The camera's `interpolatingMoveTo` call uses `attemptMoveTo` instead. DirPlayer's former method applies Z-up stacking behavior to this Y-up game, sending the physics camera far above its target. After each attempted move, assigning the camera body's position back to itself invokes the runtime's missing W3D synchronization. The original stepped collision checks remain, and the follow camera settles behind the player instead of inside the astronaut.
6. The gravity thumb's score channel is puppeted during gameplay so score tweening cannot overwrite its script-controlled position. `CheckWindowRescale` reapplies the original gravity-to-position formula before its unchanged-size return; `endSprite` releases the channel. The original drag handler and gravity calculation are retained.

Changed functions are appended with checked branch targets and updated code pointers. The name table adds `getNetMessage` and `puppet`, normalizes the Havok spelling and aliases the camera movement method. Other live game resources remain byte-identical except size/map bookkeeping. The script validates instruction boundaries and records original/adapted hashes in `public/game/compatibility.json`. Disable **Browser compatibility fixes** under diagnostics and relaunch to compare the baseline.

These are compatibility changes, not replacement terrain or fake physics/server responses. A partial upstream Rust source patch for the first two issues is also saved at `patches/dirplayer-0.8.1-source.patch` for a future runtime rebuild; the current local player uses the movie adapter instead and retains the official runtime.

**Test 3D startup** under diagnostics starts a fresh player session (click **Click to Play** again), then automatically jumps to the original avatar/3D initialization frame with a temporary debugger breakpoint immediately before `makeAServerConnection`. It does not set TermsOfUse or simulate a successful login. On success it removes the temporary breakpoint from the saved list but leaves the VM paused for scene inspection. Restart to return to ordinary interactive startup. Normal gameplay connects through local `/mus` to the legacy server; remote rejection or protocol incompatibility can still return the client to login.

Verification: the adapted game completes `makeTerrain` and `SetupPhysics`, clears both script errors, and reaches the actual Multiuser connection to local `/mus`. The offline test visibly renders lunar terrain, rocks and the original menu and reports “3D setup verified · paused for offline inspection.” Text-to-texture and missing-mesh warnings remain; movement, physics fidelity and multiplayer are unverified. Screenshot: `verification/compatibility-fixed.png`.

## World-return regression verification

The pre-fix debugger captured `Connection Script.CheckTime → logout` immediately after normal login/terms-declined startup. The bridge independently observed real server `JR` and `Logon` packets with error code 0, establishing that the old retry loop was not simply an unavailable server.

With the timestamp and callback adapters, the real join-room handler sets `OnlineConnection = 1` and `RoomNumber = 1`; the astronaut appears and the scene stays loaded beyond the former immediate logout. The page reports the joined room. **Trace world startup** creates a fresh connection test and arms a temporary logout breakpoint; **Test 3D startup** remains an offline paused test. Neither test accepts game terms or fabricates a server response. Ordinary Launch game follows the original login controls.

Bridge logs include byte counts and MUS subject/error metadata, excluding packet content, names and passwords. Browser diagnostics can still include game state. Rendering issues such as text textures and some meshes remain separate from this login-return fix. Full multi-client gameplay, chat and physics fidelity remain unverified.

## Slider and walking-camera verification

In a real legacy-server session, dragging the gravity thumb right changed `moongravity` from 125 to 226 and moved sprite 4 from `(662, 283)` to `(713, 283)`. Dragging left set gravity to 60 with the thumb at `(630, 283)`, on its track. After Enter Base, `AvatarMode` became `Walking`; both the physics and W3D camera box were 600 units behind and 150 above the player. The camera interpolated to that position without the permanent astronaut close-up. Evidence is saved in `verification/slider-camera-values.json` and `verification/slider-camera-fixed.png`.

The later planar-projection adaptation below restores terrain detail. Visor reflections, stars and text overlays still have visible rendering gaps; Earth can be seen when facing its position. Numeric remote-player models can also report empty-resource `W3D-MISS` warnings; their mesh cloning/rendering remains unresolved. These are separate from the verified slider and walking-camera fixes.

## Terrain projection and menu visibility

The terrain's original `LunarSurface` and `Dirt` textures are present and bound; this was not an outstanding asset download or server failure. GPU inspection showed that `wrapTransformList` and `textureTransformList` alias the same runtime transform. The original 90° wrap rotation then runs on a position with Z already discarded, collapsing one texture axis. The shader adapter in `public/gpu-compatibility.js` retains the complete mapping position for planar projection and normalizes pixel coordinates by texture dimensions. This restores visible lunar surface detail using the original texture. Exact original tiling and second-layer blending remain to be compared; this is not a claim of renderer parity. Setup records the adapter hash in `public/game/renderer-compatibility.json`. The official runtime bundle/WASM remain intact, and disabling Browser compatibility fixes bypasses both movie and shader adaptations.

The setup panel's sprite channels 2–17 are now visible only in `CharacterSetup`; walking/driving shows the full 3D viewport. Leaving the gameplay score restores channel visibility for the login timeline. The original return-to-setup control remains. This is an explicit browser behavior adaptation, since the packaged `SwitchAvatarMode` resizes the 3D sprite without hiding the higher score channels.

A **Lingo compatibility console** inside diagnostics can run one Lingo expression/command per line through DirPlayer's debugging API. Use `set … to …` for assignments; `=` in the expression evaluator means comparison. It requires same-origin parent messages and does not expose an HTTP execution endpoint. Diagnostics batches are limited to 48 KiB to fit the collector's 64 KiB request limit even with large decompiled handlers. Optional GPU draw observations require `gpuTrace=1` on the player URL and are off during ordinary gameplay.

Verification of the terrain/menu adaptation: a fresh ordinary player session loaded the original surface detail, joined room 1 and entered Walking mode through the original Enter Base control. Setup channels disappear while the 3D viewport expands to 800 pixels; calling the original setup transition restores their visibility on the next frame. See `verification/terrain-menu-fixed.png` and `verification/terrain-menu-diagnostics.txt`. Three bytecode branch-relocation checks, setup regeneration/hash validation, Python compilation and JavaScript syntax checks passed.

## Browser chat

The original **Global Chat** control toggles console versus speech-bubble mode; it never opened a separate chat window. DirPlayer 0.8.1 cannot create the text textures used by either view, so messages/input were invisible.

`chat.js` provides the original-style transparent console on frame 5: eight 16-pixel lines, Arial text with black shadows, and the original `ConsoleH`/bottom placement. There is no chat window, scrollbar, Chat button, or Send button. A bounded adapter mirrors each original `PrintToConsole` message and its actual `TextColor` into a 100-entry queue; only the latest eight lines are displayed. Incoming strings use textContent. Connection notices, instructions and player messages retain their original colors.

Start typing over the world or click the unboxed underscore input. Enter submits through the original handler and returns keyboard focus to the game; Escape returns to movement without sending. The original Global Chat control focuses this console and restores global-console mode; local speech bubbles remain unsupported.

Sending sets the original `TextInput` and dispatches the game's Enter key handler, preserving the original command/encryption/server path. Message strings are passed as numeric `numToChar` expressions rather than executable source. It requires the game's actual accepted-terms state and room connection; it does not accept terms or simulate server delivery. `/fps` remains an entirely local original command for verification. Public deployments disable shared browser-diagnostic collection, so these console contents are not uploaded to a shared log.

The input belongs to the sprite behavior (`browserGameplay.TextInput`), rather than a global of the same name. The adapter exposes that existing instance; sending focuses sprite 1 and holds the browser Enter key until the original handler consumes the input. Direct world typing and Enter were verified with real `Frame Rate` console responses from `/fps`. The terms guard was also exercised. Chat delivery between two players still needs a test with users who accept the original game's terms themselves.

### Player names

The same unsupported text-to-texture path hides `PlayerLabel`. `labels.js` renders yellow browser labels using actual player names and world-space head anchors snapshotted by the movie adapter. It projects those anchors with the view/projection matrices and viewport actually used by the renderer, including the offscreen texture's Y flip. It hides labels behind the camera or outside the viewport and removes departed names. Normal polling reads VM globals/datum inspection without executing Lingo expressions.

A local `BrowserTest` nameplate was visually checked above the avatar, together with working local chat commands. Remote labels use the current room's `usercode`/`userpname` and model positions; a two-client visual check remains necessary. This does not repair missing remote-avatar meshes or add terrain occlusion to labels.

## Ubuntu deployment

See [deploy/README.md](deploy/README.md) and run `./browser-test/deploy/deploy.sh root@YOUR_VPS_IP` from the project directory. The default domain is moonbasemmo.com. The installer replaces the authorized HMC frontend, configures automatic HTTPS through Caddy, and manages a loopback-only game/SMUS bridge through systemd. Production mode supports the HTTPS origin and disables shared browser logs; it does not install a replacement multiplayer backend.
