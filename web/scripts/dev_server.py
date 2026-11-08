"""Start/stop the local API independently of the launching terminal."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.run'
PID_FILE = STATE / 'server.pid'
LOG_FILE = STATE / 'server.log'
URL = 'http://127.0.0.1:8000'


def owned_pid():
    try:
        pid = int(PID_FILE.read_text())
        process = Path('/proc') / str(pid)
        command = (process / 'cmdline').read_bytes().split(b'\0')
        if (process / 'cwd').resolve() == ROOT and b'uvicorn' in command:
            return pid
    except (OSError, ValueError):
        pass
    return None


def healthy():
    try:
        with urlopen(URL + '/api/config', timeout=2) as response:
            return isinstance(json.load(response).get('catalogue'), list)
    except (OSError, URLError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    action = parser.parse_args().action
    pid = owned_pid()
    if action == 'status':
        running = healthy()
        print(f'Running: {URL}' if running else 'Server is not responding.')
        return 0 if running else 1
    if action == 'stop':
        if not pid:
            print('No background server owned by this launcher is running.')
            return 0
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if owned_pid() is None:
                PID_FILE.unlink(missing_ok=True)
                print('Background server stopped.')
                return 0
            time.sleep(.1)
        print('Shutdown requested; the server is finishing active requests.')
        return 0
    if healthy():
        print(f'Already running: {URL}')
        return 0
    if pid:
        print(f'Background server is starting (PID {pid}). Log: {LOG_FILE}')
        return 1
    STATE.mkdir(exist_ok=True)
    command = [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000']
    if (ROOT / '.env').exists():
        command += ['--env-file', str(ROOT / '.env')]
    # No PTY or inherited input/output: surviving a closed terminal does not
    # depend on the tool session that launched this process.
    with LOG_FILE.open('a') as log:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, close_fds=True)
    PID_FILE.write_text(str(process.pid))
    for _ in range(80):
        if process.poll() is not None:
            PID_FILE.unlink(missing_ok=True)
            print(f'Server exited. See {LOG_FILE}')
            return 1
        if healthy():
            print(f'Running in background: {URL} (PID {process.pid})')
            print(f'Log: {LOG_FILE}')
            return 0
        time.sleep(.1)
    print(f'Started PID {process.pid}; readiness is pending. See {LOG_FILE}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
