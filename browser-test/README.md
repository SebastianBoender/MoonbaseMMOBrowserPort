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

The bridge preserves the MUS protocol, with one compatibility translation: the encrypted `MC.content[2]` chat string is converted between the browser's byte-valued representation and the supplied Director 12 projector's UTF-8 wire representation. Player names, game messages and any chat entered are sent to that remote service. The legacy TCP leg is unencrypted. No account passwords are required by this launcher. The local HTTP host remains bound to 127.0.0.1; the bridge checks the browser Origin, only accepts masked binary messages, and does not accept a destination from the client. Browser CSP still restricts connections to the local host.

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

### Downloadable-client interoperability

The supplied Director 12 desktop runtime writes the encrypted chat string as UTF-8, while DirPlayer writes its characters as individual bytes. Even an ASCII message produces high-byte cipher characters. Without conversion, both runtimes decrypt the other one's messages into garbage, which the game's list parser then rejects silently. Browser-to-browser chat alone cannot detect this problem.

`chat_protocol.py` converts only that encrypted field, adjusts string padding and packet lengths, and reassembles split/coalesced MUS frames. All other fields and the original game encryption, terms checks, room routing, ignore list and timestamp validation are retained. Incoming older byte-based cipher strings remain supported. The browser send path remains the original game handler; the bridge never generates a chat message or logs plaintext.

The bug and correction were reproduced against the actual bundled projector in Wine using a patched **disposable copy**, a loopback MUS fixture and an isolated network namespace with the personal home directory hidden. The original package was untouched. The old browser bytes decoded incorrectly in the native runtime; translated bytes decoded to the exact expected text. The native packet was also checked through the browser VM's actual `EncryptString`/`DecryptString` functions. See [protocol evidence](../port-analysis/CHAT-COMPATIBILITY.md). A live mixed-client session on the deployed website remains a separate final check.

Run `python3 browser-test/tests/test_chat_protocol.py` and `python3 browser-test/tests/test_mus_bridge.py` for the captured native packet and bidirectional bridge regressions. `tests/native_chat_probe.py` reproduces the native test and refuses to run with a default IPv4 route; run it only inside a private network namespace. The diagnostics console command `@chat-protocol` reads the relevant game handlers in bounded chunks without sending messages.

This fix is in the Python backend. Deploy the updated backend and reconnect browser players before retesting with desktop users; refreshing static page files alone does not update a running bridge.

The original **Global Chat** control toggles console versus speech-bubble mode; it never opened a separate chat window. DirPlayer 0.8.1 cannot create the text textures used by either view, so messages/input were invisible.

`chat.js` provides the original-style transparent console on frame 5: eight 16-pixel lines, Arial text with black shadows, and the original `ConsoleH`/bottom placement. There is no chat window, scrollbar, Chat button, or Send button. A bounded adapter mirrors each original `PrintToConsole` message and its actual `TextColor` into a 100-entry queue; only the latest eight lines are displayed. Incoming strings use textContent. Connection notices, instructions and player messages retain their original colors.

Start typing over the world or click the unboxed underscore input. Enter submits through the original handler and returns keyboard focus to the game; Escape returns to movement without sending. The original Global Chat control focuses this console and restores global-console mode; local speech bubbles remain unsupported.

Sending sets the original `TextInput` and dispatches the game's Enter key handler, preserving the original command/encryption/server path. Message strings are passed as numeric `numToChar` expressions rather than executable source. It requires the game's actual accepted-terms state and room connection; it does not accept terms or simulate server delivery. `/fps` remains an entirely local original command for verification. Public deployments disable shared browser-diagnostic collection, so these console contents are not uploaded to a shared log.

The input belongs to the sprite behavior (`browserGameplay.TextInput`), rather than a global of the same name. The adapter exposes that existing instance; sending focuses sprite 1 and holds the browser Enter key until the original handler consumes the input. Direct world typing and Enter were verified with real `Frame Rate` console responses from `/fps`. The terms guard was also exercised. Chat delivery between two players still needs a test with users who accept the original game's terms themselves.

### Player names

The same unsupported text-to-texture path hides `PlayerLabel`. `labels.js` renders yellow browser labels using actual player names and world-space head anchors snapshotted by the movie adapter. It projects those anchors with the view/projection matrices and viewport actually used by the renderer, including the offscreen texture's Y flip. It hides labels behind the camera or outside the viewport and removes departed names. Normal polling reads VM globals/datum inspection without executing Lingo expressions.

A local `BrowserTest` nameplate was visually checked above the avatar, together with working local chat commands. Remote labels use the current room's `usercode`/`userpname` and model positions; a two-client visual check remains necessary. This does not repair missing remote-avatar meshes or add terrain occlusion to labels.

### Walking drift and keyboard focus

`input-compatibility.js` releases game keys when chat takes focus, the frame loses focus, the document becomes hidden, or pointer lock exits. It captures key releases before chat stops propagation and also tracks DirPlayer's hidden input. A native browser reproduction previously left `keyPressed(126)` at 1 after releasing Up over chat; the same sequence now reads 0.

The runtime's resting mesh contact path assumes Z-up, while Moonbase's terrain and gravity use Y-up. For the walking body only, the adapter disables its native GroundShape collision and supplies floor contact from the game's original `checkheight` query and authored 50-unit center offset. It updates the behavior's actual `ongroundwalk` property so original walking acceleration and idle braking run. Gravity, airborne momentum, rocket impulses and other collision pairs remain active. This is a walking terrain compatibility fallback, not a general replacement Havok implementation.

FrameMod is capped at 9 (60ms of elapsed frame time), rather than the original 99, to avoid a large steering/physics impulse after a background-tab stall. A simulated 100-second clock gap returned 9 in the VM. Browser checks covered 20-second stationary position stability, walking and stopping, jetpack ascent and landing, and unchanged horizontal position after landing. Lifecycle regression checks run with `node --test browser-test/tests/test_input_compatibility.cjs`.

### Jetpack boosters

The runtime uses a nozzle model's local position as its particle origin and shares one particle system per resource. Moonbase parents two nozzle models to the astronaut and shares a resource between them, leaving the effect at the wrong location and combining the two streams.

The adapter gives the right nozzle an independent resource (named `Particle`, in the separate model-resource namespace), copying the original setup bytecode with only the resource name changed. Both streams retain the original particle texture, yellow-to-red colors, opacity, speeds, sizes, lifetime and nozzle transforms. Each frame supplies both nozzles' world positions as emitter regions and mirrors the original resource's thrust switch to the second stream. Particle counts start at zero to avoid the runtime's initial one-shot burst, then become the original 20 per nozzle on first thrust. The original control logic still controls timing; neither stream loops after Ctrl release. Both native particle streams were visually checked during actual Ctrl thrust.

### Viewport tilt and mooncart fallback

The score supplies sprite 1 with rotation −2.6° and skew 1.18° in this runtime, turning the entire 3D view into a slanted quadrilateral. `CheckWindowRescale` now resets those two 2D transforms every frame; the 3D follow camera retains its own rotation.

The native Havok mesh-contact and suspension implementation sends the Y-up cart sliding sideways, flipping, or separating its chassis and seat. The movie adapter now parks unattended carts and uses a limited Y-up vehicle fallback while driving. The original `DrivePlayer` acceleration, reverse, steering, and spacebar handbrake impulses remain in control. The adapter integrates their velocity using the original `FrameMod * 0.022` timestep, applies gravity and the original `checkheight` floor with a 50-unit ride height, and holds the seat assembly ten units above the chassis. Yaw is accumulated separately to avoid unstable Euler-angle round trips. Both native cart bodies remain inactive during the shared Havok step, and their two native dashpots have zero strength.

This is an interim vehicle controller: articulated suspension, pitch/roll over terrain, rock/ramp collisions, and collisions with other bodies are not reproduced for the cart. Walking and jetpack still use their existing physics path. Chat passes +/= to the original vehicle exit handler while driving.

Browser verification covered stationary parking, straight forward drive with zero yaw, reverse, steering, spacebar braking (speed reduced to 0.0821), +/= exit back to Walking, re-entry, and jetpack ascent/landing beside the parked cart. Across the 20-second post-exit trace the cart stayed at `(2100, -682.1325, -1106.6247)` with zero velocity. The viewport read rotation 0 and skew 0. Screenshot: `verification/cart-and-viewport-fixed.png`.

For a 20-second read-only trace, enter `@physics` in the local Lingo diagnostics console and hold game keys in the stage. It samples actual input, gravity, thrust, and body positions/velocities without changing them. At gravity 125, a three-second Ctrl test rose from Y −664 to Y +689 and landed back at the original floor. The user's reported failure had gravity 234: the original impulse (100 / mass 30 per FrameMod) only overcomes gravity below about 151.5 with the authored 0.022 timestep. Lower the gravity slider for takeoff; the adapter does not silently change the original rocket power.

### Retro site layout and mobile sizing

The outer site follows the supplied old Maid Marian layout: black surroundings, a wood-toned masthead, amber textured content panel, serif type, orange links, left navigation, and dotted section dividers. Credits explicitly name Maid Marian Entertainment as the original creator, link to `http://www.maidmarian.com/`, thank Heath from Discord for hosting multiplayer, and describe this project as an unofficial port made for nostalgia. DirPlayer is also credited.

Below 600px the navigation wraps above the content. The game frame keeps its 800:550 aspect ratio, while the original 800 × 550 player scales to fit inside it. The pointer and chat/nameplate overlays continue to use the canvas's rendered bounds. Touch controls appear automatically on phones and coarse-pointer devices, and can also be toggled in the toolbar. The external pad supports simultaneous fingers for movement plus jetpack, dance, vehicle brake and exit. Controls release on cancellation, focus loss, rotation, fullscreen changes, and lost parent heartbeats. Native name and chat fields open the phone keyboard; name entry still requires tapping the original Login button and reviewing the original terms. Enter Base uses the original game button. Fullscreen gives the entire viewport to the stage, with translucent movement and action buttons over it. Chat stays at the top left; the compact top-right menu contains Touch controls, Modern quality and Exit fullscreen. Safe-area insets keep controls away from notches and the home indicator. Scaled canvas taps are translated back to the original stage coordinates. Runtime options and diagnostics are collapsed below the public content.

Browser verification covered the desktop layout, creator/server credits and links, diagnostic navigation, player launch through the original login screen, and 390px/320px phone viewports with no horizontal document overflow. Screenshots: `verification/retro-site-desktop.png` and `verification/retro-site-mobile.png`.

### Soccer ball stability and update caching

The native Z-up solver also affected `TheBall`: an unattended baseline trace acquired sideways velocity, then reached Y −64,073 while the terrain was around −1,442. The ball now uses a limited Y-up heightfield fallback in every game mode, including character setup. Original proximity-kick impulses remain unchanged. Eight substeps per capped frame integrate gravity and sample the original `checkheight` floor with the visible sphere's 80-unit radius. Impacts use the body's restitution; small bounces settle and ground speed loses at most `friction * |gravity| * dt` per substep. Total speed is capped at 700 world units/second. The ball is inactive during the shared native Havok step so incompatible contacts cannot kick it sideways or under the map. Rock, vehicle, and other rigid-body contacts and visual rolling spin are not reproduced by this interim ball controller.

Browser checks covered initial drop/rest, a `(500, -2000, 0)` high-speed impact, original walking proximity kicks, floor-penetration recovery, and gravity 234. The initial ball settled at `(0, -759, 0)` on terrain Y −839. A real kick landed and rolled to `(1000, 211.0194, 6676.4520)` on terrain Y 131.0194, then remained stationary. High-gravity recovery settled at `(1300, -593.3333, 1000)` on terrain Y −673.3333. The live trace stayed around FrameMod 2.1–2.55, and the original local `/fps` command printed normal text at 67 FPS. `@physics` now includes ball position, velocity, and terrain height.

An old bordered chat with a Chat/Send button and literal `<DatumRef(...)>` lines indicates stale app files mixed with a newer console/movie adapter. The current chat remains the original-style transparent overlay. Modified-time revalidation can retain stale files when a release has older timestamps than a previously cached deployment. The host now serves mutable app and game assets with `Cache-Control: no-store` and ignores conditional cache headers for them. The pinned vendor runtime retains normal revalidation. Regression checks send future-dated conditional requests for HTML, chat JS, CSS, and the adapted movie and require fresh 200 responses. Reinstall/restart the backend and refresh the page after updating. A clean browser test verified the transparent console and decoded system messages plus the original local `/fps` command. Screenshot: `verification/ball-and-chat-fixed.png`.

## Ubuntu deployment

See [deploy/README.md](deploy/README.md) and run `./browser-test/deploy/deploy.sh root@YOUR_VPS_IP` from the project directory. The default domain is moonbasemmo.com. The installer replaces the authorized HMC frontend, configures automatic HTTPS through Caddy, and manages a loopback-only game/SMUS bridge through systemd. Production mode supports the HTTPS origin and disables shared browser logs; it does not install a replacement multiplayer backend.


Mobile input verification: the 390px browser viewport exercised native name entry, a scaled Login tap, Enter Base, held movement, jetpack lift and a local `/fps` chat command. The 320px layout had no horizontal overflow; the earlier landscape layout kept the pad beside the stage (superseded by the immersive overlay). Automated tests cover independent/same-key fingers, cancel/lost capture, mode restrictions, origin checks, focus/visibility cleanup and the input heartbeat timeout. Physical Android/iOS touch and software keyboards still need device testing. Run `node --test browser-test/tests/*.cjs` for input regressions.

Deployment packages stamp local script and stylesheet URLs in both HTML documents with each asset's SHA-256 prefix. This forces browsers with cached assets from older releases to fetch the matching chat/UI files even if the older response allowed caching. After the first upgrade to this packaging change, open the site with a fresh query string (for example `/?update=asset-versions`) or hard-refresh the page.

Fullscreen now expands the stage to fit the display while preserving its aspect ratio. The collapsed game menu provides Exit and Touch controls. Opening it releases all held movement keys. Browsers without element fullscreen, or denying the request, use an in-page viewport-filling fallback; browser chrome remains visible there. Escape first dismisses the menu, then exits the fallback even with game focus. On iPhone, Share → Add to Home Screen and launch the saved app to remove browser chrome. The manifest and Apple web-app metadata support a standalone launch; no service worker or offline caching is installed. The original stage aspect ratio is preserved, so wider screens retain side space behind the overlay controls. Physical iPhone/Android testing remains necessary.


### Separate Modern client

The default entry remains Original. Choose **Modern client** (or open `/?client=modern`) for optional 720p, 1080p, 1440p/QHD (2K) and 4K/UHD rendering. The original aspect ratio and authored UI are preserved; quality changes do not reconnect multiplayer. Modern includes capability checks, safe rollback, context recovery and local frame-time diagnostics. See [MODERN-CLIENT.md](MODERN-CLIENT.md) for dimensions, architecture, build provenance, validation and limitations.

Mouse-wheel camera zoom works in both clients while frame 5 is running. Scroll down to widen the 3D view, down to 50% of the original projection scale; scroll up to restore 100%. It never zooms closer than the authored POV. This is a lens/projection adjustment, so camera collisions, physics, UI and input coordinates stay unchanged. Nameplates use the adjusted projection. Browser pinch zoom and scrolling over chat/forms remain available. Relaunching resets the view to 100%.

Off-map gravity fix (2026-11-16): `makeTerrain` creates a finite 64 × 64 heightmap mesh, spaced 600 units apart, spanning X/Z −19500 through 18300. The original `checkheight` clamps sample indices and extrapolates outside that mesh. Our Y-up contact workaround previously treated that height as an infinite floor, making it possible to walk beyond the Moon toward Earth (X 16342.9, Z −32853.2). Floor contact for walking, the cart and the ball is now guarded by the actual mesh footprint, derived from the heightmap dimensions. Gravity and rocket impulses are unchanged; the original fall-below−4000 recovery remains in place. Live diagnostics verified gravity vector (0, −125, 0), an off-map player falling from Y −2100 to −2265.2207 with velocity −204.6, subsequent respawn at X/Z 0/0, and the ball falling outside the map. Regression tests execute the emitted guard at all four edges, corners, Earth and nonsquare map dimensions.

Player shadow correction (2026-11-16): the original `lambert7` shader uses the `ShadowAlpha` texture and a near-black diffuse color. DirPlayer's textured-material default substituted white for that diffuse, producing a pale spotlight under the avatar. The compatibility movie enables `useDiffuseWithTexture` on `lambert7` during world initialization. This retains the original texture, alpha, size and terrain tracking, while leaving astronaut, terrain and other materials unchanged. Live inspection verified the pale disc becomes a soft dark shadow.
