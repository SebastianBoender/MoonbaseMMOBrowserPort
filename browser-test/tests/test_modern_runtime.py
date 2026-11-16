"""Check shipped runtime provenance and that patches reject unknown upstream code."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'runtime-modern'
spec=importlib.util.spec_from_file_location('patch_runtime',SOURCE/'patch_runtime.py')
patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)

class ModernRuntimeTests(unittest.TestCase):
    def test_distributed_bundle_matches_its_source_manifest(self):
        manifest=json.loads((SOURCE/'manifest.json').read_text())
        packed=(SOURCE/'dirplayer-modern.js.gz').read_bytes()
        self.assertEqual(hashlib.sha256(packed).hexdigest(),manifest['archive_sha256'])
        self.assertEqual(hashlib.sha256(gzip.decompress(packed)).hexdigest(),manifest['bundle_sha256'])
        self.assertEqual(hashlib.sha256((SOURCE/'patch_runtime.py').read_bytes()).hexdigest(),manifest['patch_sha256'])
        self.assertEqual(hashlib.sha256((SOURCE/'upstream-source.tar.gz').read_bytes()).hexdigest(),manifest['source_sha256'])

    def test_patch_applies_to_supplied_pinned_source_and_rejects_reapplication(self):
        files=['vm-rust/src/player/stage.rs','vm-rust/src/rendering_gpu/webgl2/mod.rs','vm-rust/src/rendering_gpu/webgl2/scene3d.rs','dirplayer-js-api/index.js']
        with tempfile.TemporaryDirectory() as directory,tarfile.open(SOURCE/'upstream-source.tar.gz') as archive:
            root=Path(directory)
            for name in files:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(archive.extractfile(f'dirplayer-rs-7f632b416b55ec351341feda4db2a444564217aa/{name}').read())
            patch.apply(root)
            with self.assertRaises(ValueError):patch.apply(root)
