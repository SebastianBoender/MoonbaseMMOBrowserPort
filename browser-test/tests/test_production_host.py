"""Check the HTTPS proxy boundary without exposing a public listener."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve


class ProductionHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(serve.Handler, directory=str(serve.PUBLIC)))
        cls.server.production = True
        cls.server.allowed_origins = ('https://moonbasemmo.com',)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, origin=None):
        connection = HTTPConnection(*self.server.server_address, timeout=3)
        headers = {'Origin': origin} if origin else {}
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_https_csp_and_game_assets(self):
        status, headers, body = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('wss://moonbasemmo.com', headers['Content-Security-Policy'])
        self.assertIn(b'Moonbase', body)

    def test_shared_diagnostics_are_not_public(self):
        self.assertEqual(self.request('GET', '/api/diagnostics')[0], 404)

    def test_diagnostics_are_acknowledged_without_writing_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            original = serve.LOGS
            serve.LOGS = Path(folder)
            try:
                status, _, body = self.request('POST', '/api/diagnostics', '{"events":[{"message":"private"}]}', 'https://moonbasemmo.com')
                self.assertEqual(status, 200)
                self.assertIn(b'"saved": 0', body)
                self.assertFalse(list(Path(folder).iterdir()))
            finally:
                serve.LOGS = original

    def test_cross_origin_diagnostic_posts_are_rejected(self):
        self.assertEqual(self.request('POST', '/api/diagnostics', '{"events":[]}', 'https://evil.example')[0], 403)

    def test_directory_listing_is_disabled(self):
        self.assertEqual(self.request('GET', '/vendor/')[0], 404)

    def test_updated_assets_cannot_reuse_future_dated_cached_chat(self):
        for path in ('/', '/player.html', '/chat.js', '/player.css', '/game/moonbase-browser.dir'):
            with self.subTest(path=path):
                connection = HTTPConnection(*self.server.server_address, timeout=3)
                connection.request('GET', path, headers={'If-Modified-Since': 'Wed, 01 Jan 2031 00:00:00 GMT'})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                self.assertTrue(response.read())
                connection.close()


if __name__ == '__main__':
    unittest.main()
