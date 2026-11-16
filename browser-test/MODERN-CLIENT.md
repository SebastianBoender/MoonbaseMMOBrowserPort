# Original and Modern clients

The default `/` and `/?client=original` launch the verified official DirPlayer 0.8.1 bundle with Original rendering. `/?client=modern` is a separate opt-in entry point using the isolated Modern runtime. The game movie and server protocol are shared. Switching client navigates/restarts; switching resolution within Modern keeps the movie and multiplayer socket alive.

## Presets and legacy framing

All gameplay and authored UI coordinates remain 800 × 550 (16:11). The presets represent 16:9 display classes; the actual game occupies the original aspect ratio, with black bars in a wider display. No widescreen camera modification, texture replacement, modern lighting or new physics is included.

| Selection | Display class | Actual full-world render target |
|---|---|---|
| Original | Original | 800 × 550 |
| 720p | 1280 × 720 | 1047 × 720 |
| 1080p | 1920 × 1080 | 1571 × 1080 |
| 1440p / QHD (2K) | 2560 × 1440 | 2095 × 1440 |
| 4K / UHD | 3840 × 2160 | 3142 × 2160 |

Dimensions are rounded to pixels. In Character Setup, the world sprite is narrower because the original menu occupies the right side. The renderer reports this smaller 3D target rather than pretending the menu is part of the world.

The default quality is Original. Modern remembers the user's explicit quality choice locally. It does not multiply that target by devicePixelRatio, change it on resize/rotation, or repeatedly adjust quality automatically. A smaller display can downsample a larger selected target. High quality is more GPU-intensive; it does not fix interpreter/physics/network lag.

## Implementation

- `public/resolution.js`: presets, capability checks and frame-time summaries.
- `public/coordinates.js`: shared authored/render conversion for browser text and VM input.
- `public/graphics.js`: separate entry points, quality selectors (normal/fullscreen), persistence, diagnostics and recovery controls.
- `public/resolution-player.js`: trusted-parent control messages, asynchronous stage resizing, safe rollback, context recovery and performance reports.
- `public/gpu-compatibility.js`: existing terrain fix plus observational 3D viewport/cadence and live allocation counters. No generic texture-resize interception is used.
- `runtime-modern/`: complete guarded source patch, pinned upstream source archive, GPL license, build scripts, compressed bundle and SHA-256 provenance. The official bundle/WASM is never patched or replaced.

The Modern runtime keeps stage bounds logical while applying the existing stage scale to renderer output. Its 3D framebuffer uses the scaled sprite rectangle; this is true geometry rendering at the selected resolution. Camera overlay positions remain authored. Legacy text textures are rasterized at authored dimensions and composited into the larger stage; they are not restyled. New color/depth targets are checked for framebuffer completeness before old attachments are deleted. Missing/failed targets roll back. GPU limits are checked before selection, but limits alone cannot guarantee adequate device memory or speed.

Input APIs receive render-pixel positions and the VM converts them to movie coordinates. Chat uses logical viewport dimensions. Nameplate projection uses the real 3D matrices/viewport and scales only its logical head offset. Fullscreen changes presentation size, not selected rendering quality. Held keys/pointers release during quality changes and context loss.

## Failure and performance behavior

Unsupported presets are disabled after capability discovery. A failed change restores the previous quality; a late scene allocation failure returns to Original. WebGL context loss releases input. When restoration is available, the runtime recreates graphics at Original quality while retaining the movie; unrecoverable cases explicitly ask for relaunch. Diagnostics include a recovery test button.

Graphics diagnostics expose actual stage/scene dimensions, graphics limits, tracked live framebuffer/renderbuffer/texture allocations and the last 240 scene-draw intervals. Median, p95 and frames over 50 ms are reported. These are draw-cadence observations, not GPU timing-query measurements. Background periods and quality-change warm-up samples are cleared. Sustained slow draws offer Original quality without automatic oscillation. Data stays in the browser unless the user downloads diagnostics; it is not added to shared server logs.

## Validation and limits

Automated checks cover preset geometry, capability constraints, coordinate conversion, frame-time statistics, trusted-message boundaries, Original isolation, rollback, context recovery, runtime source/artifact hashes and exact-match source-patch guards, alongside existing chat/input/host/relay regressions.

Browser verification records actual offscreen 3D viewports for all presets, native login/name entry, original setup controls, world entry, quality cycling in a single session, allocation counts, fullscreen and mobile-sized layouts. The local test hardware is not representative of every player. Physical Android/iOS browsers and low-memory GPUs need device testing; they must not be described as verified merely because a desktop viewport is narrow.

## Build, update and rollback

Normal `setup.py` / `deploy.sh --package-only` verifies and decompresses the included Modern runtime; the Ubuntu VPS does not need Rust, Node or npm. Packaged HTML references content-versioned JS/CSS; the derived runtime URL includes its bundle hash. The installer checks that both runtimes and the Modern manifest are present. Existing atomic-release deployment/rollback remains in use.

For a developer rebuild, see `runtime-modern/README.md`. The complete corresponding source and build recipe are also shipped beneath `/vendor/dirplayer-0.8.1/modern-source/` using direct filenames. To disable Modern, users can return to Original without changing their server or account.
