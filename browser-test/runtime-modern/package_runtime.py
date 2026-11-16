"""Package the reproducible Modern bundle and provenance for VPS setup."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import subprocess

ROOT=Path(__file__).resolve().parent
SOURCE_SHA256='c261d07dfc55555abaac63a9b7450f8d5d66696220633fbc30b2ab7177a55a53'
COMMIT='7f632b416b55ec351341feda4db2a444564217aa'

def package(source, archive):
    source=Path(source);archive=Path(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SOURCE_SHA256:raise ValueError('Source checksum mismatch')
    data=(source/'dist-polyfill/dirplayer-polyfill.js').read_bytes()
    packed=gzip.compress(data,compresslevel=9,mtime=0)
    (ROOT/'dirplayer-modern.js.gz').write_bytes(packed)
    if archive.resolve() != (ROOT/'upstream-source.tar.gz').resolve():
        shutil.copyfile(archive,ROOT/'upstream-source.tar.gz')
    manifest={'upstream_version':'0.8.1','upstream_commit':COMMIT,'source_sha256':SOURCE_SHA256,
      'source_url':f'https://github.com/igorlira/dirplayer-rs/tree/{COMMIT}',
      'bundle_sha256':hashlib.sha256(data).hexdigest(),'archive_sha256':hashlib.sha256(packed).hexdigest(),
      'patch_sha256':hashlib.sha256((ROOT/'patch_runtime.py').read_bytes()).hexdigest(),
      'cargo_lock_sha256':hashlib.sha256((source/'vm-rust/Cargo.lock').read_bytes()).hexdigest(),
      'npm_lock_sha256':hashlib.sha256((source/'package-lock.json').read_bytes()).hexdigest(),
      'toolchain':{'rust':'1.91.1','wasm_bindgen':'0.2.108','profile':'release (opt-level=3, fat LTO)','node':subprocess.check_output(['node','--version'],text=True).strip(),'npm':subprocess.check_output(['npm','--version'],text=True).strip()},
      'changes':['fixed logical stage for moonbaseModern=1','transactional FBO replacement and deletion','authored camera overlay coordinates','legacy text rasterized at authored size','observational diagnostics callbacks'],
      'license':'GPL-3.0-only'}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copyfile(source/'LICENSE',ROOT/'LICENSE')
    print(f'Packaged Modern runtime: {len(data):,} bytes, SHA256 {manifest["bundle_sha256"]}')

if __name__=='__main__':package(*sys.argv[1:])
