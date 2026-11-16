import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('version_assets', ROOT / 'deploy/version_assets.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AssetVersions(unittest.TestCase):
    def test_both_documents_use_exact_asset_hashes_and_changes_get_new_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            for asset in (ROOT / 'public').iterdir():
                if asset.is_file():
                    shutil.copyfile(asset, public / asset.name)
            module.version_assets(public)
            before = (public / 'player.html').read_text()
            for name in ('index.html', 'player.html'):
                html = (public / name).read_text()
                urls = re.findall(r'(?:src|href)="/([\w-]+\.(?:js|css))\?v=([a-f0-9]+)"', html)
                self.assertTrue(urls)
                self.assertNotRegex(html, r'(?:src|href)="/[\w-]+\.(?:js|css)"')
                for asset, digest in urls:
                    self.assertEqual(digest, hashlib.sha256((public / asset).read_bytes()).hexdigest()[:16])
            module.version_assets(public)
            self.assertEqual(before, (public / 'player.html').read_text())
            (public / 'chat.js').write_text('// next release\n')
            module.version_assets(public)
            self.assertNotEqual(before, (public / 'player.html').read_text())
            self.assertIn('id="touch-controls"', (public / 'index.html').read_text())
