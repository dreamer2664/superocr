#!/usr/bin/env python3
"""Offline Linux/POSIX W2 archive check; never asserts native/browser coverage.
Requires an independently prepared virtualenv Python (no system site packages).
python3 tools/verify_w2_package.py --archive ZIP --python VENV/bin/python --out JSON
No credentials, upload, production-reader edit, or canonical-suite generation.
"""
import argparse, ast, base64, hashlib, json, os, pathlib, socket, subprocess
import tempfile, time, urllib.request, zipfile
ROOT = pathlib.Path(__file__).resolve().parent.parent

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', required=True, type=pathlib.Path)
    ap.add_argument('--python', required=True)
    ap.add_argument('--out', required=True, type=pathlib.Path)
    a=ap.parse_args(); a.archive=a.archive.resolve(); a.python=str(pathlib.Path(a.python).resolve()) if not pathlib.Path(a.python).is_symlink() else str(pathlib.Path(a.python).absolute())
    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    constants={}
    for node in ast.parse((ROOT/'app/build_bundle.py').read_text()).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in {'COPY_FILES','COPY_DIRS','LAUNCHER_SH','LAUNCHER_BAT','REQUIREMENTS','INSTALL_MD'}:
                    constants[target.id]=ast.literal_eval(node.value)
    env=os.environ.copy()
    for k in ('PYTHONPATH','PYTHONHOME','GIT_DIR','GIT_WORK_TREE'): env.pop(k,None)
    receipt={'source_sha':source_sha,'archive_name':a.archive.name,'archive_sha256':digest(a.archive),
             'limits':['Linux/POSIX only','No native Windows/macOS run','No browser screen-picker interaction','Demo GT is NOT canonical accuracy'], 'checks':{},'logs':{}}
    def check(name,ok):
        receipt['checks'][name]=bool(ok)
        if not ok: raise AssertionError(name)
    with tempfile.TemporaryDirectory(prefix='w2-clean-') as tmp:
        clean=pathlib.Path(tmp)
        with zipfile.ZipFile(a.archive) as z:
            for info in z.infolist():
                p=pathlib.PurePosixPath(info.filename)
                check('safe archive paths',not p.is_absolute() and '..' not in p.parts)
            z.extractall(clean)
        dirs=[p for p in clean.iterdir() if p.is_dir()];check('one bundle root',len(dirs)==1)
        b=dirs[0];ver=json.loads((b/'version.txt').read_text());receipt['version']=ver
        check('exact full source SHA',ver['git_commit']==source_sha and len(source_sha)==40)
        check('12 demo items',ver['demo_items']==12)
        check('no repository or prebuilt cache',(not (b/'.git').exists()) and not (b/'.template-cache').exists())
        shipped=list(constants['COPY_FILES'])
        for d in constants['COPY_DIRS']:
            shipped.extend(str(p.relative_to(ROOT)) for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        receipt['source_file_hashes']={p:digest(b/p) for p in sorted(shipped)}
        check('all shipped source/font/model bytes match HEAD',all(digest(ROOT/p)==digest(b/p) for p in shipped))
        for name,key in [('start.sh','LAUNCHER_SH'),('start.command','LAUNCHER_SH'),('requirements.txt','REQUIREMENTS'),('INSTALL.md','INSTALL_MD')]:
            check(name+' matches builder',(b/name).read_text()==constants[key])
        check('Windows launcher matches builder text',(b/'start.bat').read_bytes()==constants['LAUNCHER_BAT'].replace('\n','\r\n').encode())
        receipt['font_hashes']={p.name:digest(p) for p in sorted((b/'fonts').glob('*.ttf'))}
        check('eight fonts and redistributable license',len(receipt['font_hashes'])==8 and (b/'fonts/LICENSE-DejaVu.txt').exists())
        meta=subprocess.check_output([a.python,'-I','-c','import sys,json,numpy,PIL;print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,pillow=PIL.__version__,prefix=sys.prefix,base_prefix=sys.base_prefix)))'],cwd=b,env=env,text=True)
        receipt['runtime']=json.loads(meta);check('isolated virtualenv',receipt['runtime']['prefix']!=receipt['runtime']['base_prefix'])
        def run_self(label,args=(),fallback=False):
            cmd=[a.python,'-I','webapp/server.py','--suites','demo-suite','--selftest',*args]
            if fallback:
                code="import sys,runpy,pathlib;sys.path.insert(0,str(pathlib.Path.cwd()));import generator as G;G._FONT_CANDIDATES=[str(G._LOCAL_FONT_DIR/pathlib.Path(p).name) for p in G._FONT_CANDIDATES];sys.argv=['webapp/server.py','--suites','demo-suite','--selftest'];runpy.run_path('webapp/server.py',run_name='__main__')"
                cmd=[a.python,'-I','-c',code]
            t=time.perf_counter();r=subprocess.run(cmd,cwd=b,env=env,capture_output=True,text=True,timeout=600)
            receipt['logs'][label]={'rc':r.returncode,'seconds':round(time.perf_counter()-t,3),'stdout':r.stdout,'stderr':r.stderr}
            return r
        r=run_self('fresh_selftest');check('fresh selftest 12 items zero drift',r.returncode==0 and '12 items, 0 failure(s) -> PASS' in r.stdout)
        r=run_self('bundled_fonts_only_selftest',fallback=True);check('all12 reproduce with system font paths replaced by bundle paths',r.returncode==0 and '12 items, 0 failure(s) -> PASS' in r.stdout)
        man=b/'demo-suite/easy/manifest.jsonl';original=man.read_text();rows=original.splitlines();row=json.loads(rows[0]);row['expected_lex']='INTENTIONALLY WRONG';rows[0]=json.dumps(row);man.write_text('\n'.join(rows)+'\n')
        r=run_self('tampered_expectation',['--selftest-limit','1']);man.write_text(original)
        check('tampered expectation reports drift and exit1',r.returncode==1 and 'DRIFT' in r.stdout)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        log=clean/'server.log'
        with log.open('w') as fh:
            proc=subprocess.Popen([a.python,'-I','webapp/server.py','--port',str(port),'--host','127.0.0.1','--suites','demo-suite'],cwd=b,env=env,stdout=fh,stderr=fh)
            try:
                url=f'http://127.0.0.1:{port}'
                deadline=time.monotonic()+30
                while True:
                    try:health=json.load(urllib.request.urlopen(url+'/api/health',timeout=2));break
                    except Exception:
                        if proc.poll() is not None or time.monotonic()>deadline:raise
                        time.sleep(.2)
                receipt['health']=health;check('health full provenance and fonts8',health['app_version']['git_commit']==source_sha and health['fonts']==8)
                outputs=[]
                for split in ('easy','hard'):
                    for line in (b/f'demo-suite/{split}/manifest.jsonl').read_text().splitlines():
                        row=json.loads(line);payload={'image':base64.b64encode((b/f'demo-suite/{split}'/row['image']).read_bytes()).decode(),'route':'lex'}
                        req=urllib.request.Request(url+'/api/ocr',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                        t=time.perf_counter();out=json.load(urllib.request.urlopen(req,timeout=120))
                        outputs.append({'split':split,'id':row['id'],'family':row['family'],'label':row['label'],'expected_lex':row['expected_lex'],'actual':out['text'],'matches_expectation':out['text']==row['expected_lex'],'gt_exact':out['text']==row['label'],'route':out['route'],'server_ms':out['server_ms'],'wall_seconds':round(time.perf_counter()-t,3)})
                receipt['lex_demo_items']=outputs;check('all12 live lex reproduce expectations',all(x['matches_expectation'] and x['route']=='lex' for x in outputs))
                receipt['demo_gt_summary']={split:{'exact':sum(x['gt_exact'] for x in outputs if x['split']==split),'count':sum(x['split']==split for x in outputs)} for split in ('easy','hard')}
            finally:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        receipt['logs']['server']=log.read_text()[-10000:]
    receipt['pass']=all(receipt['checks'].values());a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('source_sha','archive_sha256','runtime','demo_gt_summary','pass')},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
