# MoonbaseMMOBrowserPort

A browser compatibility port of the original Moonbase Director game using DirPlayer 0.8.1 / WebAssembly. Includes a reversible movie adapter, renderer adaptations, browser chat and nameplates, and a fixed WebSocket-to-TCP bridge to the legacy multiplayer server at `pigyak.com:1626`.

## Run locally

Place your original `MB_2010-10-08.exe` in this directory, then run:

```bash
python3 browser-test/run.py
```

Open http://127.0.0.1:8080 and launch the game. Setup extracts the movie without executing the Windows binary, verifies the pinned runtime download, and generates a separate compatibility copy. Python 3.10+ is sufficient.

The original game package, extracted movies, downloaded runtimes and local diagnostics are not committed. The original assets are required to build/run; runtime licenses do not grant rights to redistribute the game's assets.

## Deploy to Ubuntu

For the prepared domain **moonbasemmo.com**, point DNS at your VPS and run:

```bash
./browser-test/deploy/deploy.sh root@YOUR_VPS_IP
```

The installer configures Caddy HTTPS, a systemd service, and the multiplayer bridge. It replaces the existing HMC web frontend as requested and backs up its Caddy configuration. See [deployment instructions](browser-test/deploy/README.md) for ports, manual upload, service commands and rollback.

## Status

Login/room joins, terrain detail, walking-camera positioning, gravity dragging and menu transitions have been exercised in the browser. Chat and player names use browser text because the runtime cannot render the original text textures. Remaining limitations include stars, reflections, text textures, exact physics/rendering fidelity and some remote-avatar mesh paths. This is a preservation/compatibility experiment, not a full native browser rewrite or a new multiplayer backend.

See [runtime and compatibility notes](browser-test/README.md), [port analysis](port-analysis), and [static security review](security-review). Multiplayer traffic goes to the legacy service; this project does not impersonate server success.
