#!/usr/bin/env python3
"""Loopback game host, optionally behind an HTTPS reverse proxy."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from mus_bridge import proxy

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
LOGS = ROOT / "logs"


class Handler(SimpleHTTPRequestHandler):
    rbufsize = 0
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm",
                      ".dir": "application/octet-stream", ".js": "text/javascript",
                      ".webmanifest": "application/manifest+json"}

    def end_headers(self):
        immutable_runtime = urlsplit(self.path).path.startswith('/vendor/')
        self.send_header("Cache-Control", "no-cache" if immutable_runtime else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        websocket_origins = ' '.join(origin.replace('https://', 'wss://').replace('http://', 'ws://')
                                     for origin in getattr(self.server, 'allowed_origins', ()))
        if not getattr(self.server, 'production', False):
            websocket_origins += ' ws://127.0.0.1:* ws://localhost:*'
        self.send_header("Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' blob:; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self' data: blob:; media-src 'self' blob: data:; "
            f"worker-src 'self' blob:; connect-src 'self' blob: {websocket_origins}; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        super().end_headers()

    def send_head(self):
        # Release files can have older mtimes than a browser's cached copy
        # (e.g. SCP preserves timestamps, followed by a git-based install).
        # Date-based 304 responses would mix old chat JS/CSS with a new movie.
        # Always send mutable app/game assets; keep the pinned vendor runtime
        # revalidatable rather than downloading its large WASM on every launch.
        if not urlsplit(self.path).path.startswith('/vendor/'):
            for header in ('If-Modified-Since', 'If-None-Match'):
                if header in self.headers:
                    del self.headers[header]
        return super().send_head()

    def json_response(self, status, value):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            manifest = json.loads((PUBLIC / "game" / "manifest.json").read_text())
            return self.json_response(200, {"runtime": "DirPlayer 0.8.1", "movie": manifest,
                "multiplayer": "Legacy server pigyak.com:1626 via local WebSocket-to-TCP bridge at /mus."})
        if path == "/api/diagnostics":
            if getattr(self.server, 'production', False):
                return self.send_error(404)
            log = LOGS / "browser.jsonl"
            lines = log.read_text().splitlines()[-300:] if log.exists() else []
            return self.json_response(200, {"events": [json.loads(line) for line in lines]})
        if path == "/mus":
            return proxy(self)
        if self.path.endswith("/") and path != "/":
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/diagnostics":
            return self.send_error(404)
        origin = self.headers.get("Origin")
        allowed = getattr(self.server, 'allowed_origins', None) or (f"http://{self.headers.get('Host')}",)
        if origin and origin not in allowed:
            return self.send_error(403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                return self.send_error(413)
            value = json.loads(self.rfile.read(length))
            events = value.get("events", [])
            if not isinstance(events, list) or len(events) > 100:
                return self.send_error(400)
            if getattr(self.server, 'production', False):
                # Keep diagnostics client-side on a public deployment.
                return self.json_response(200, {"saved": 0, "collection": "disabled"})
            LOGS.mkdir(exist_ok=True)
            with (LOGS / "browser.jsonl").open("a") as log:
                for event in events:
                    log.write(json.dumps({"received": time.time(), "event": event}) + "\n")
            return self.json_response(200, {"saved": len(events)})
        except (ValueError, TypeError, AttributeError):
            return self.send_error(400)

    def list_directory(self, path):
        return self.send_error(404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--public-origin", help="Exact HTTPS origin allowed through the reverse proxy")
    parser.add_argument("--production", action="store_true", help="Disable shared browser diagnostics and per-packet MUS logs")
    args = parser.parse_args()
    if args.public_origin:
        origin = urlsplit(args.public_origin)
        if origin.scheme != 'https' or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
            parser.error('--public-origin must be an HTTPS origin without a path or credentials')
    if args.production and not args.public_origin:
        parser.error('--production requires --public-origin')
    if not (PUBLIC / "game" / "moonbase.dir").exists():
        parser.error("Run python3 browser-test/setup.py first")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(PUBLIC)))
    server.production = args.production
    server.allowed_origins = (args.public_origin,) if args.public_origin else (
        f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}')
    print(f"Moonbase test environment: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
