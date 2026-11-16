#!/usr/bin/env python3
"""Prepare the pinned browser runtime and relocate the embedded Director movie."""
import hashlib
import json
from pathlib import Path
import struct
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "0.8.1"
ARCHIVE_SHA256 = "6f5000412c50833345a630ade25fb70359dc4e1aae66352c80de7da77542162c"
SOURCE_SHA256 = "6d7b81d5d1e76ca6ee7ca2f1fc4286ab19a62a344417f88d229f677280b43a3a"
URL = f"https://github.com/igorlira/dirplayer-rs/releases/download/v{VERSION}/dirplayer-polyfill-{VERSION}.zip"


def prepare_runtime():
    vendor = ROOT / "public" / "vendor" / f"dirplayer-{VERSION}"
    marker = vendor / "release.json"
    if marker.exists():
        manifest = json.loads(marker.read_text())
        for name, expected in manifest["files"].items():
            if hashlib.sha256((vendor / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Runtime file changed: {name}. Remove vendor directory and rerun setup.")
        print(f"Verified installed DirPlayer {VERSION}")
        return
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    archive = cache / f"dirplayer-polyfill-{VERSION}.zip"
    if not archive.exists():
        print(f"Downloading official DirPlayer {VERSION} browser release…", flush=True)
        with urllib.request.urlopen(URL, timeout=90) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("DirPlayer archive does not match the published release digest")
    vendor.mkdir(parents=True, exist_ok=True)
    files = {}
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            dest = (vendor / entry.filename).resolve()
            if not dest.is_relative_to(vendor.resolve()):
                raise ValueError("Unsafe archive path")
            if not entry.is_dir():
                files[entry.filename] = hashlib.sha256(package.read(entry)).hexdigest()
        package.extractall(vendor)
    marker.write_text(json.dumps({"version": VERSION, "url": URL,
        "archive_sha256": ARCHIVE_SHA256, "files": files}, indent=2) + "\n")
    print(f"Verified and installed DirPlayer {VERSION}")


def extract_movie():
    source = ROOT.parent / "MB_2010-10-08.exe"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unexpected game version; refusing to use offsets from another package")
    start = 0x495504
    assert data[start:start + 4] == b"XFIR" and data[start + 8:start + 12] == b"39VM"
    size = struct.unpack_from("<I", data, start + 4)[0] + 8
    movie = bytearray(data[start:start + size])
    mmap_abs = struct.unpack_from("<I", movie, 24)[0]
    mmap = mmap_abs - start
    assert movie[mmap:mmap + 4] == b"pamm"
    header, stride, allocated, used = struct.unpack_from("<HHII", movie, mmap + 8)
    assert header == 24 and stride == 20 and used <= allocated
    struct.pack_into("<I", movie, 24, mmap)
    relocated = 0
    payloads = []
    for index in range(used):
        pos = mmap + 8 + header + index * stride
        tag = bytes(movie[pos:pos + 4])
        length, absolute = struct.unpack_from("<II", movie, pos + 4)
        if tag in (b"eerf", b"knuj", b"\0\0\0\0"):
            # Removed entries can refer to overwritten data; they are not resources.
            struct.pack_into("<I", movie, pos + 8, 0)
            continue
        relative = absolute - start
        if not (0 <= relative <= size - 8 and relative + 8 + length <= size):
            raise ValueError(f"Chunk {index} lies outside the embedded movie")
        assert bytes(movie[relative:relative + 4]) == tag
        struct.pack_into("<I", movie, pos + 8, relative)
        relocated += 1
        if tag not in (b"XFIR", b"pami", b"pamm"):
            original = data[absolute + 8:absolute + 8 + length]
            assert bytes(movie[relative + 8:relative + 8 + length]) == original
            payloads.append({"id": index, "tag": tag[::-1].decode("ascii"),
                "bytes": length, "sha256": hashlib.sha256(original).hexdigest()})
    target = ROOT / "public" / "game"
    target.mkdir(parents=True, exist_ok=True)
    (target / "moonbase.dir").write_bytes(movie)
    # A second, independent pass checks the relocated map from file offset zero.
    recovered = (target / "moonbase.dir").read_bytes()
    check_map = struct.unpack_from("<I", recovered, 24)[0]
    for index in range(used):
        pos = check_map + 8 + header + index * stride
        tag = recovered[pos:pos + 4]
        if tag in (b"eerf", b"knuj", b"\0\0\0\0"):
            continue
        length, offset = struct.unpack_from("<II", recovered, pos + 4)
        assert recovered[offset:offset + 4] == tag
        assert offset + 8 + length <= len(recovered)
    manifest = {"source": source.name, "source_sha256": SOURCE_SHA256,
        "movie_sha256": hashlib.sha256(movie).hexdigest(), "movie_bytes": len(movie),
        "original_movie_offset": start, "relocated_resources": relocated,
        "unaltered_payloads": payloads, "runtime_version": VERSION,
        "changes": "Index/resource offsets only; Lingo, graphics and other resource payloads unchanged."}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Recovered {len(movie):,}-byte movie; relocated {relocated} resource pointers; payloads preserved")
    from compatibility import prepare
    prepare(ROOT)


def prepare_diagnostics():
    # Keep the official release intact. A derived copy adds notification hooks
    # at public VM callbacks, without changing interpreter or gameplay behavior.
    vendor = ROOT / "public" / "vendor" / f"dirplayer-{VERSION}"
    original = (vendor / "dirplayer-polyfill.js").read_text()
    instrumented = original
    hooks = {
        'function onMovieLoaded(C){': 'movie-loaded',
        'function onScriptError$1(C){': 'script-error',
        'function onDebugMessage(C){': 'debug-message',
        'function onScopeListChanged(C){': 'scope-list',
        'function onFrameChanged(C){': 'frame',
    }
    for needle, kind in hooks.items():
        if instrumented.count(needle) != 1:
            raise ValueError(f"Diagnostic hook no longer matches release: {needle}")
        hook = f'window.dispatchEvent(new CustomEvent("moonbase-runtime",{{detail:{{kind:"{kind}",value:C}}}}));'
        instrumented = instrumented.replace(needle, needle + hook)
    target = vendor / "dirplayer-diagnostic.js"
    target.write_text(instrumented)
    (vendor / "diagnostic-hooks.json").write_text(json.dumps({
        "base_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "derived_sha256": hashlib.sha256(instrumented.encode()).hexdigest(),
        "hooks": hooks, "note": "Observational callback events only; original release retained."
    }, indent=2) + "\n")
    shader = ROOT / "public" / "gpu-compatibility.js"
    (ROOT / "public" / "game" / "renderer-compatibility.json").write_text(json.dumps({
        "runtime_version": VERSION,
        "adapter": "/gpu-compatibility.js",
        "adapter_sha256": hashlib.sha256(shader.read_bytes()).hexdigest(),
        "scope": "Moonbase planar terrain projection only (u_uv_proj_mode == 5)",
        "changes": "Preserve full mapping position through aliased wrap/texture transform; normalize by texture pixel dimensions.",
        "bypass": "Disable Browser compatibility fixes and relaunch.",
        "limitations": "Original planar tiling and second-layer blending fidelity are not yet established. Sky, text textures and reflection issues remain."
    }, indent=2) + "\n")
    print("Prepared observational VM diagnostics (official bundle retained)")


if __name__ == "__main__":
    prepare_runtime()
    extract_movie()
    prepare_diagnostics()
