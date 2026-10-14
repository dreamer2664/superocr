#!/usr/bin/env python3
"""Cross-platform bootstrap + bounded watchdog. No silent selftest failures."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / 'baseline.py').is_file() else HERE.parent.parent
SERVER = ROOT / 'apps/captcha-studio/server.py'


def available(python):
    return subprocess.run([str(python), '-c', 'import numpy, PIL; '
                           'assert int(numpy.__version__.split(".")[0]) == 2; '
                           'assert int(PIL.__version__.split(".")[0]) == 12'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def run_logged(command, logfile):
    """Read stdout to the screen and log, then return the CHILD status, not tee's."""
    with logfile.open('a', encoding='utf-8') as log:
        with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                              errors='replace', bufsize=1) as proc:
            try:
                for line in proc.stdout:
                    print(line, end='', flush=True)
                    log.write(line);log.flush()
                return proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
                raise


def main():
    if sys.version_info < (3, 10):
        print('Python 3.10 or newer is required. No server started.', file=sys.stderr)
        return 2
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8488)
    p.add_argument('--no-browser', action='store_true')
    p.add_argument('--skip-selftest', action='store_true', help='diagnostics only; prints a warning')
    p.add_argument('--no-install', action='store_true', help='do not create a venv or download dependencies')
    p.add_argument('--max-restarts', type=int, default=2)
    args = p.parse_args()
    if not 1 <= args.port <= 65535 or not 0 <= args.max_restarts <= 5:
        p.error('invalid port or restart budget')
    os.chdir(ROOT)
    python = Path(sys.executable)
    if not available(python):
        if args.no_install:
            print('NumPy 2.x / Pillow 12.x missing or incompatible. Install requirements.txt, or allow bootstrap. No server started.')
            return 2
        venv = ROOT / '.venv'
        python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            print('Creating local virtual environment…', flush=True)
            subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
        if not available(python):
            print('Installing NumPy/Pillow. First setup needs internet access…', flush=True)
            subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT/'requirements.txt')], check=True)
    log = ROOT / 'studio.log'
    if args.skip_selftest:
        print('WARNING: explicit --skip-selftest; font/generation integrity not checked.')
    else:
        print('Checking bundled fonts, all 18 generation arms, determinism and ZIP export…', flush=True)
        status = run_logged([str(python), str(SERVER), '--selftest'], log)
        if status:
            print(f'SELF-TEST FAILED (exit {status}); server NOT started. See studio.log.', flush=True)
            return status
    command = [str(python), str(SERVER), '--port', str(args.port)]
    if not args.no_browser:
        command.append('--browser')
    for attempt in range(args.max_restarts + 1):
        status = run_logged(command, log)
        if status == 0:
            return 0
        if attempt == args.max_restarts:
            print(f'Server exited {status}; restart budget exhausted. See studio.log.')
            return status
        print(f'Server exited {status}; restarting ({attempt+1}/{args.max_restarts})…', flush=True)
        time.sleep(1 + attempt)
    return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nStopped by user; watchdog will not restart.', flush=True)
        raise SystemExit(0)
    except (OSError, subprocess.CalledProcessError) as exc:
        print('Setup failed: ' + str(exc) + '\nNo successful startup claimed. See README.md.', file=sys.stderr)
        raise SystemExit(2)
