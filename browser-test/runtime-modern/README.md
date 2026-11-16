# Moon Base Modern runtime

Derived from DirPlayer 0.8.1, commit `7f632b416b55ec351341feda4db2a444564217aa`, under GPL-3.0-only. The Original client retains the checksum-verified official runtime. Modern uses a separately built bundle; no official files are overwritten.

`patch_runtime.py` contains the complete changes: fixed authored stage bounds while framebuffer dimensions grow; transactional 3D framebuffer replacement with deletion of old attachments; camera overlay projection and legacy text rasterization in authored coordinates; observational diagnostics hooks. Geometry, textures, camera FOV and game logic are unchanged.

`upstream-source.tar.gz` is the exact upstream source archive, verified by the manifest. Together with the patch, build/package scripts, upstream lockfiles and LICENSE, it supplies the corresponding source. The same files are distributed at `/vendor/dirplayer-0.8.1/modern-source/` (use direct filenames; directory listing is disabled).

For developer rebuilds, install Rust 1.91.1 with `wasm32-unknown-unknown`, wasm-bindgen-cli 0.2.108, and Node/npm. Run `./browser-test/runtime-modern/build.sh`. It extracts the source, applies the patch with exact-match guards, builds release WASM (opt-level 3, fat LTO), generates bindings, installs locked npm dependencies with install scripts disabled, and builds the official polyfill. Output is deterministic gzip plus SHA-256 provenance. Vite post-build notices about missing Ruffle/Xtras are expected: setup installs this bundle beside the complete verified official runtime assets.

VPS deployment does not compile Rust or install npm dependencies: setup verifies and decompresses the included runtime artifact. The original Windows game is never executed.
