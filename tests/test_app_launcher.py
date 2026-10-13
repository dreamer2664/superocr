#!/usr/bin/env python3
"""W2 Unix launcher regression: preserve the selftest status across logging.

No OCR, package installation, network, or real server is involved. Extract
LAUNCHER_SH via AST and provide a fake Python executable. Exercise success,
failure, and explicit --no-selftest under POSIX sh. The Windows launcher is
not exercised by this test; do not treat this as a Windows runtime receipt.

    python3 tests/test_app_launcher.py
"""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def launcher_source():
    tree = ast.parse((ROOT / 'app/build_bundle.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'LAUNCHER_SH'
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError('LAUNCHER_SH missing')


STUB = '''#!/bin/sh
case "$*" in
  *--selftest*)
    echo "SELFTEST_RAN status=${STUB_SELFTEST_STATUS:-0}"
    echo "SELFTEST_STDERR" >&2
    exit "${STUB_SELFTEST_STATUS:-0}" ;;
  *--port*) echo "SERVER_STUB_STARTED"; exit 0 ;;
  *) exit 0 ;;
esac
'''


def run_case(shell, text, status, skip=False):
    with tempfile.TemporaryDirectory(prefix='w2-launcher-') as tmp:
        root = Path(tmp)
        bindir = root / 'bin'
        bindir.mkdir()
        for name in ('python3', 'python'):
            executable = bindir / name
            executable.write_text(STUB, encoding='utf-8')
            executable.chmod(0o755)
        start = root / 'start.sh'
        start.write_text(text, encoding='utf-8')
        syntax = subprocess.run([shell, '-n', str(start)], capture_output=True, text=True)
        assert syntax.returncode == 0, syntax.stderr
        env = os.environ.copy()
        env['PATH'] = str(bindir) + os.pathsep + env.get('PATH', '')
        env['STUB_SELFTEST_STATUS'] = str(status)
        proc = subprocess.run(
            [shell, str(start)] + (['--no-selftest'] if skip else []),
            cwd=root, env=env, capture_output=True, text=True, timeout=10,
        )
        logfile = root / 'app.log'
        log = logfile.read_text(encoding='utf-8') if logfile.exists() else ''
        return proc, log


def main():
    shell = shutil.which('sh')
    if os.name == 'nt' or not shell:
        print('SKIP: POSIX sh unavailable; Windows launcher not covered')
        return 0
    text = launcher_source()
    failures = []
    checks = 0

    def check(name, condition, details=''):
        nonlocal checks
        checks += 1
        print(('PASS  ' if condition else 'FAIL  ') + name)
        if not condition:
            failures.append(name)
            if details:
                print(details)

    for status, skip, label in ((0, False, 'success'), (1, False, 'failure'),
                               (7, False, 'non-one failure'), (1, True, 'explicit skip')):
        proc, log = run_case(shell, text, status, skip)
        output = proc.stdout + proc.stderr
        check(label + ': launcher completes after stub server exits 0',
              proc.returncode == 0, output)
        check(label + ': existing start-after-warning policy retained',
              output.count('SERVER_STUB_STARTED') == 1, output)
        check(label + ': selftest invocation matches explicit skip',
              ('SELFTEST_RAN' in output) == (not skip), output)
        check(label + ': failure warning matches actual selftest status',
              ('SELF-TEST FAILED' in output) == (status != 0 and not skip), output)
        check(label + ': wrong-reads warning matches actual selftest status',
              ('reads may be WRONG' in output) == (status != 0 and not skip), output)
        check(label + ': stdout and stderr logged unless skipped',
              ('SELFTEST_RAN' in log and 'SELFTEST_STDERR' in log) == (not skip), log)
    print(f'\n{checks} checks, {len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
