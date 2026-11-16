# Moonbase browser and multiplayer feasibility

Analysis date: 15 November 2026. Deployment assumption: Ubuntu **24.04 LTS** on a VPS. No game executable, Xtra, or game script was executed during this analysis. Browser compatibility has not yet been tested.

## Recommendation

First run a bounded preservation experiment: recover a standalone Director movie, test it in a pinned DirPlayer browser build, and connect two browser clients to a private compatible backend. If rendering, movement, physics and networking work with limited fixes, this can deliver the nostalgic game with much less reconstruction. If the experiment exposes fundamental gaps, switch to a TypeScript/Babylon.js rewrite using recovered assets and Lingo as reference.

For substantial future gameplay changes, prefer the modern rewrite even if emulation works. It provides explicit control over the simulation and server. Do not commit to a full rewrite before assessing the recoverable material and emulator compatibility.

The VPS is a straightforward part of either route. The difficult work is recovering the game, reproducing its movement/physics, and replacing the missing multiplayer backend.

## What this package actually contains

The EXE wraps Adobe Director rather than providing an editable modern engine port. A structured inspection found an uncompressed little-endian RIFX/MV93 movie at EXE offset `0x495504`, with a declared container length of **2,267,654 bytes**. The resource map uses absolute EXE offsets. A simple byte slice will leave those references incorrect: extraction must relocate the resource-map offsets and the index-map pointer, or use a projector-aware extractor. Validate the output with an independent Director parser before calling it playable.

The movie map identifies:

| Resource | Observed count | Meaning for a port |
| --- | ---: | --- |
| `Lscr` | 28 | Compiled Lingo scripts available for decompilation |
| `Lnam` | 4 | 1,243 total symbol-table entries, including duplicate names across tables |
| `CASt` | 81 | Cast-member records, not necessarily 81 independently exportable assets |
| `BITD` | 23 | Bitmap-data chunks; decoded images still need export and inspection |
| `XMED` | 25 | Mixed external-media payloads |
| `XMED` beginning `3DEM` | 1 | A 326,420-byte embedded Shockwave 3D scene payload |
| `XMED` with an early `FWS` signature | 4 | Embedded small Flash assets that must be tested/exported too |

The internal casts are named `Internal`, `LoginScreen`, `AvatarScreem`, and `NewScreens`. The visible game label is Moon Base Version 1.7d.

Gameplay symbols include `WalkPlayer`, `DrivePlayer`, `MakeRocketPack`, `MoveCamera`, `SetupPhysics`, `moongravity`, `makeTerrain`, `createrocks`, `sourceMap`, `hFactor`, `gridsize`, `Dance`, and `HipHop`. This suggests a combination of imported 3D assets, animation, procedural terrain and scripted physics. These names do not establish the algorithms or tuning constants; decompilation and observation are still required.

Networking strings include `connectToNetServer`, `sendNetMessage`, `CharPositionMessageHandler`, `system.script.changeroom`, `system.list.users`, `system.list.rooms`, and `system.report`. The connection script contains `pigyak.com` and `MoonBase0429`. These are embedded references, not verified live endpoints or confirmed credentials. Do not connect to that host as part of development. The port number, login flow, message structures and authorization model remain to be recovered.

A room-full message explicitly mentions **25 players maximum**. Start with that room model; the evidence does not show a seamless large-scale MMO world.

The Xtra dependency list also references `Enhancer.x32`, which is absent from the folder. Symbols suggest legacy display-resolution and task-switching functions. These may require a browser-compatible stub or a small Lingo patch if called. Whether browser-mode execution avoids them needs testing.

Reproduce the structural findings with `python3 port-analysis/inspect_movie.py`. It writes resource metadata and symbol tables without evaluating Lingo.

## Option A: preserve the original client in a browser

[DirPlayer](https://github.com/igorlira/dirplayer-rs) provides a browser WASM runtime and embeddable polyfill. Its [current release notes](https://github.com/igorlira/dirplayer-rs/releases) describe Shockwave3D, Havok, animation, and Multiuser improvements. This makes it a credible experiment, not proof that Moonbase is compatible. Pin a version and test this specific movie rather than depending on a moving CDN URL.

The [embedding documentation](https://github.com/igorlira/dirplayer-rs/wiki/Polyfill---Embedding) supports self-hosted movie loading and socket endpoint mappings. Because this movie embeds Flash, use the matching bundled Flash integration when needed; the documentation warns that stock Ruffle is not interchangeable with that integration. Ruffle alone cannot run the Director game.

Preservation deployment:

```text
Browser: DirPlayer + recovered Director movie
    | HTTPS assets and secure WebSocket messages
    v
Nginx on Ubuntu:443
    |-- static site, pinned player files, movie/assets
    `-- /mus -> fixed-target WebSocket-to-TCP bridge
                       `-> private compatible Multiuser backend
```

The bridge only changes transport. It does not implement room joining, user lists, chat routing, state messages, or game-specific server scripts. DirPlayer's [Multiuser documentation](https://github.com/igorlira/dirplayer-rs/wiki/Multiuser-Xtra) describes this distinction.

[OpenSMUS](https://opensmus.sourceforge.net/) is a Java/Linux candidate for protocol experiments. Its own documentation states that server-side Lingo is not implemented, using Java extensions instead. Moonbase's `system.script.changeroom` and other custom commands mean a stock installation must not be assumed sufficient. No server code or configuration exists in this package. Recover the expected messages and implement the game-specific behavior, or write a narrow compatible backend. Review/update old dependencies before using an old server distribution publicly.

Success conditions before adopting this route:

1. Movie opens without native Windows DLLs or Xtras; login and Flash UI respond.
2. Terrain, avatar skinning, camera, walking, rover and jetpack behave acceptably.
3. Two independent browser sessions see movement, animations and chat correctly.
4. Room changes, joins/leaves, disconnects and reconnects do not corrupt state.
5. Chrome and Firefox work; check Safari separately if it is a target.
6. Server independently controls moderation and permissions; movie passwords and client-side ban checks are not treated as authority.

Use this route if it preserves the experience with modest compatibility changes. Switch if it requires rebuilding major rendering/physics subsystems, or gameplay development becomes constrained by the legacy VM. Avoid indefinitely implementing missing emulator functionality for one game.

## Option B: modern browser client and multiplayer server

My preferred rewrite stack is **TypeScript + Babylon.js + a shared simulation package + Colyseus on Node.js**, with GLB/glTF assets. Babylon has the scene, animation, particle and browser rendering features needed here; [its specifications](https://www.babylonjs.com/specifications/) cover those capabilities. Start with a WebGL2 client; WebGPU can be optional after browser testing.

Use [modern Havok WASM](https://doc.babylonjs.com/features/featuresDeepDive/physics/havokPlugin/) for an initial physics comparison. The familiar name does not make it compatible with the old Havok Xtra, serialized data, or original tuning. Recreate collision shapes, forces, gravity, spring/dashpot behavior and constraints. Prove headless server initialization, deployment packaging and CPU cost before committing to this physics integration for the shared simulation.

[Colyseus](https://docs.colyseus.io/getting-started/server) supplies room/session/state infrastructure and authoritative networking options. The game simulation, validation rules and movement feel remain our work. Its [deployment documentation](https://docs.colyseus.io/deployment) supports normal self-hosted Node deployments behind Nginx.

Rewrite deployment:

```text
Browser: Babylon scene + input + prediction + interpolated remote players
    | HTTPS static assets / WSS game connection
    v
Nginx on Ubuntu:443
    |-- static client and versioned assets
    `-- Colyseus room process
           |-- shared fixed-step movement / collision simulation
           `-- optional database for accounts, bans and saved settings
```

Send input commands to the server; the server validates and advances the simulation, then publishes state. Predict local movement for responsiveness, reconcile with server updates, and interpolate other players. Do not rely on clients sending arbitrary trusted positions or on old client-side moderation checks. No deterministic lockstep is required.

As initial engineering settings, evaluate a 60 Hz simulation and 10–20 Hz state updates, then measure and adjust. These are proposed starting points, not recovered original rates. Compare rover/jetpack behavior under simulated latency before adding features. Preserve original room capacity initially and load-test it rather than promising a capacity from VPS specifications alone.

Guest names and ephemeral rooms can come first. Add a persistent database only when accounts, moderation records or other persistence need it; PostgreSQL is a reasonable eventual choice. Keep moderation decisions server-side, rate-limit chat/connections, and render chat as text.

Three.js is also viable, but I would choose Babylon for this game because its integrated game-oriented features reduce the systems we need to assemble. Godot/Unity would be reasonable with an existing editable project/team workflow; this package provides neither, so those choices do not avoid asset recovery or behavior reconstruction.

## Recover assets and behavior before rebuilding

1. Keep the original package immutable and work on copies. Extract and normalize the embedded movie; validate its chunk references.
2. Try [ProjectorRays](https://github.com/ProjectorRays/ProjectorRays) to reconstruct Lingo and an editable movie. Its documented output is recovered Director projects, not JavaScript or a finished browser game. Verify this Director version and recovered handlers rather than assuming full decompiler coverage.
3. Export cast members. [Director Cast Ripper](https://github.com/n0samu/DirectorCastRipper) documents W3D export specifically in its Director 12 variant, plus bitmap/text/audio export. Native Director-based tools belong in an isolated recovery environment, not on the production VPS.
4. Convert static world geometry and textures to modern assets. [Shockwave 3D World Converter](https://github.com/tomysshadow/Shockwave-3D-World-Converter) exports OBJ/MTL/images but explicitly cannot export bones. It is therefore not a complete avatar/animation pipeline. Preserve the W3D original and evaluate a rig-aware parser/exporter or runtime inspection for skeletal data. Rebuilding/retargeting animation is a fallback, not assumed necessary or lossless.
5. Recover terrain generation inputs and rules as well as meshes. Exporting a W3D alone may miss terrain built from the `sourceMap` bitmap by Lingo.
6. Recover movement constants, coordinate axes, scale, collision shapes, camera offsets, room logic and network messages. Record reference behavior in an isolated original-runtime environment after security scanning, if needed. Match gravity, acceleration, braking, jump/jetpack behavior and animation timing before cosmetic improvements.

The first modern-renderer milestone should be the recovered map, one avatar, faithful camera and movement. The next should be two browser clients in the same room with chat. Placeholder scenery alone would not demonstrate a faithful port.

## Ubuntu VPS sizing and operation

Ubuntu 24.04 LTS is suitable; [Canonical's release notes](https://documentation.ubuntu.com/release-notes/24.04/) list standard security maintenance through 2029. Use supported current runtime releases and pinned application dependencies.

For an initial small-community experiment, budget **2–4 vCPU and 4–8 GB RAM** as a starting envelope, not a measured capacity or a minimum requirement. Shared CPU contention and server physics cost matter more than the vintage game's graphics. Rendering happens in each player's browser; a GPU VPS is not needed for either proposed architecture. Build the player/client off-server and deploy artifacts if build memory would compete with active rooms.

Use Nginx with HTTPS and WebSocket upgrades, one managed backend process initially, private internal server ports, restart policies and persistent-volume backups. A systemd service or Docker Compose is enough; choose one operational approach. Expose only the web entry point and restricted administration access. If using a transport bridge, configure a fixed backend target so it cannot become a general-purpose outbound proxy.

Track room/player counts, tick duration, event-loop delay, memory and outbound bandwidth. Scale by distributing rooms when measurements justify it. Accounts/database growth and seamless worlds are separate features, not requirements for restoring this game.

## Decision and next milestone

**Proceed with recovery and a two-client DirPlayer feasibility test first.** Keep its backend internal while recovering the custom protocol. If it passes the movement/rendering/multiplayer gates with limited changes, use it for the initial nostalgic release. If it fails those gates, reuse the recovered material in the Babylon/Colyseus implementation.

The investigation has not run a browser build, exported a usable GLB, decompiled Lingo, or demonstrated a working server. Those are explicit next milestones, not completed results. Exact schedule depends principally on emulator compatibility, rig/animation recovery, and missing custom server behavior.

There is no game-asset license in this folder; clarify redistribution permission before public hosting. Tool licenses do not supply a license to Moonbase's assets.
