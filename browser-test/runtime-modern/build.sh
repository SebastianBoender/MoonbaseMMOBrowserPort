#!/usr/bin/env bash
# Developer rebuild only. VPS deploys use the included verified binary/source.
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
COMMIT=7f632b416b55ec351341feda4db2a444564217aa
[[ $(rustc --version) == 'rustc 1.91.1 '* ]] || { echo 'Install Rust 1.91.1 and target wasm32-unknown-unknown.' >&2; exit 1; }
[[ $(wasm-bindgen --version) == 'wasm-bindgen 0.2.108' ]] || { echo 'Install wasm-bindgen-cli 0.2.108.' >&2; exit 1; }
mkdir -p "$ROOT/../.cache"
BUILD_DIR=$(mktemp -d "$ROOT/../.cache/modern-build.XXXXXXXX")
python3 - "$ROOT/upstream-source.tar.gz" "$BUILD_DIR" <<'PY'
import hashlib,sys,tarfile
from pathlib import Path
archive=Path(sys.argv[1]);assert hashlib.sha256(archive.read_bytes()).hexdigest()=='c261d07dfc55555abaac63a9b7450f8d5d66696220633fbc30b2ab7177a55a53'
with tarfile.open(archive) as source:source.extractall(sys.argv[2],filter='data')
PY
SOURCE="$BUILD_DIR/dirplayer-rs-$COMMIT"
python3 "$ROOT/patch_runtime.py" "$SOURCE"
(cd "$SOURCE/vm-rust" && cargo build --release --locked --target wasm32-unknown-unknown)
wasm-bindgen --target web --out-dir "$SOURCE/vm-rust/pkg" "$SOURCE/vm-rust/target/wasm32-unknown-unknown/release/vm_rust.wasm"
printf '%s\n' '{"name":"vm-rust","version":"0.1.0","type":"module","main":"vm_rust.js","types":"vm_rust.d.ts","files":["vm_rust.js","vm_rust_bg.wasm","vm_rust.d.ts"],"sideEffects":["./snippets/*"]}' > "$SOURCE/vm-rust/pkg/package.json"
(cd "$SOURCE" && npm ci --ignore-scripts --no-audit --no-fund && npm run build-polyfill)
python3 "$ROOT/package_runtime.py" "$SOURCE" "$ROOT/upstream-source.tar.gz"
echo "Rebuild retained for inspection: $SOURCE"
