#!/usr/bin/env python3
"""Build the G1 downloadable studio from an explicit file allowlist.

No datasets, local credentials, reports, hidden files, virtualenvs or caches are
copied. A dirty tree requires --allow-dirty and is clearly stamped development.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'apps/captcha-studio'
FILES = ['generator.py', 'baseline.py', 'reader.py', 'preclassify.py',
         'requirements.txt', 'tools/gen_hard_corpus.py', 'tools/lex_projection.py',
         'tools/reader_lex.py', 'models/glyphcnn-v2.npz', 'models/preclass_centroids.npz',
         'readers/glyphcnn.py', 'readers/segmentation.py', 'readers/piece_cnn.py',
         'apps/captcha-studio/engine.py', 'apps/captcha-studio/server.py',
         'apps/captcha-studio/static/index.html', 'apps/captcha-studio/static/app.js',
         'apps/captcha-studio/static/style.css']
SH = '''#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "Python 3.10+ is required. See README.md."; exit 1; fi
exec "$PY" launch.py "$@"
'''
BAT = '''@echo off\r
cd /d "%~dp0"\r
where py >nul 2>nul\r
if %errorlevel% equ 0 (\r
  py -3 launch.py %*\r
) else (\r
  python launch.py %*\r
)\r
set "STUDIO_EXIT=%errorlevel%"\r
if not "%STUDIO_EXIT%"=="0" (\r
  echo Studio stopped with an error. See studio.log and README.md.\r
  pause\r
)\r
exit /b %STUDIO_EXIT%\r
'''


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def build(output: Path, allow_dirty: bool = False):
    revision = git('rev-parse', 'HEAD')
    dirty = bool(git('status', '--porcelain'))
    if dirty and not allow_dirty:
        raise RuntimeError('Commit the source before a release build (or use --allow-dirty for development)')
    stamp = revision[:12] + ('-dev' if dirty else '')
    name = 'superocr-captcha-studio-' + stamp
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    directory = output / name
    if directory.exists():
        raise RuntimeError('Output directory already exists; choose a fresh --out directory')
    directory.mkdir()
    fonts = json.loads((APP / 'fonts/SHA256SUMS.json').read_text())
    copies = [(path, path) for path in FILES]
    copies += [('apps/captcha-studio/fonts/' + name, 'apps/captcha-studio/fonts/' + name)
               for name in [*fonts, 'SHA256SUMS.json', 'LICENSE_DEJAVU.txt']]
    copies += [('apps/captcha-studio/launcher.py', 'launch.py'),
               ('apps/captcha-studio/README.md', 'README.md')]
    for source, target in copies:
        p = ROOT / source
        if not p.is_file() or p.is_symlink():
            raise RuntimeError('Missing/unsafe allowlisted input: ' + source)
        dest = directory / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
    (directory / 'start.sh').write_text(SH, encoding='utf-8')
    (directory / 'start.command').write_text(SH, encoding='utf-8')
    (directory / 'start.bat').write_bytes(BAT.encode('utf-8'))
    for f in ['start.sh', 'start.command']:
        (directory / f).chmod(0o755)
    hashes = {str(p.relative_to(directory)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(directory.rglob('*')) if p.is_file()}
    info = {'product': 'superocr CAPTCHA Studio', 'recipe': 'g1-studio-v1',
            'revision': revision, 'dirty': dirty, 'clean_source': not dirty,
            'release': False, 'distribution': 'review-candidate',
            'review_status': 'review candidate; consult linked PR for current approvals',
            'accuracy_target_met': False, 'files_sha256': hashes}
    (directory / 'studio-build.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n')
    archive = output / (name + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if not p.is_file():
                continue
            rel = str(p.relative_to(output)).replace('\\', '/')
            item = zipfile.ZipInfo(rel, (2020, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (0o100755 if p.name in ('start.sh', 'start.command')
                                  else 0o100644) << 16
            z.writestr(item, p.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / (name + '.sha256.txt')).write_text(digest + '  ' + archive.name + '\n')
    return {'directory': str(directory), 'zip': str(archive), 'sha256': digest,
            'bytes': archive.stat().st_size, 'revision': revision, 'dirty': dirty,
            'files': len(hashes) + 1}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--allow-dirty', action='store_true')
    args = p.parse_args()
    print(json.dumps(build(args.out, args.allow_dirty), indent=2))


if __name__ == '__main__':
    main()
