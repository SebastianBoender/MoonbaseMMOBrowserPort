#!/usr/bin/env python3
"""Start/stop the loopback test server independently of the invoking terminal."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8080)
parser.add_argument('--stop', action='store_true')
args = parser.parse_args()
logs = ROOT / 'logs'
logs.mkdir(exist_ok=True)
pidfile = logs / f'server-{args.port}.pid'
url = f'http://127.0.0.1:{args.port}'

if args.stop:
    if not pidfile.exists():
        sys.exit('No managed server PID file for this port.')
    pid = int(pidfile.read_text())
    try:
        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if str(ROOT / 'serve.py').encode() not in cmdline:
            sys.exit('PID no longer belongs to this server; refusing to signal it.')
        os.kill(pid, signal.SIGTERM)
    except FileNotFoundError:
        pass
    pidfile.unlink(missing_ok=True)
    print('Moonbase test server stopped.')
    sys.exit(0)

try:
    with urllib.request.urlopen(url + '/api/status', timeout=2) as response:
        if json.load(response).get('runtime') == 'DirPlayer 0.8.1':
            print(f'Moonbase test server already running: {url}')
            sys.exit(0)
except (OSError, ValueError):
    pass

import setup
setup.prepare_runtime()
setup.extract_movie()
setup.prepare_diagnostics()
with (logs / 'server.log').open('a') as output:
    child = subprocess.Popen([sys.executable, str(ROOT / 'serve.py'), '--port', str(args.port)],
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
pidfile.write_text(str(child.pid))
for _ in range(40):
    if child.poll() is not None:
        pidfile.unlink(missing_ok=True)
        sys.exit('Server exited. See browser-test/logs/server.log (the port may be in use).')
    try:
        with urllib.request.urlopen(url + '/api/status', timeout=1) as response:
            if response.status == 200:
                print(f'Moonbase test environment: {url}\nPID {child.pid}; logs: {logs}')
                break
    except OSError:
        time.sleep(0.1)
else:
    child.terminate()
    pidfile.unlink(missing_ok=True)
    sys.exit('Server failed its readiness check. See browser-test/logs/server.log.')
