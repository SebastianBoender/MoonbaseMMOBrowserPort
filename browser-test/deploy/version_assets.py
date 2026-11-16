#!/usr/bin/env python3
"""Give packaged HTML content-addressed URLs for our mutable JS and CSS.

Response cache headers cannot evict assets cached by an older server release.
New URLs ensure the HTML and its scripts/styles belong to the same package.
"""
import hashlib
from pathlib import Path
import re
import sys


def version_assets(public):
    public = Path(public)
    pattern = re.compile(r'(?P<prefix>\b(?:src|href)=\")/(?P<name>[A-Za-z0-9_-]+\.(?:js|css))(?:\?[^\"]*)?(?P<end>\")')
    for name in ('index.html', 'player.html'):
        page = public / name
        def replace(match):
            asset = public / match['name']
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:16]
            return f'{match["prefix"]}/{match["name"]}?v={digest}{match["end"]}'
        page.write_text(pattern.sub(replace, page.read_text()))


if __name__ == '__main__':
    version_assets(sys.argv[1])
