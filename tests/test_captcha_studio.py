#!/usr/bin/env python3
"""G1 isolated generator/app controls; uses no canonical evaluation dataset.

Run: python3 tests/test_captcha_studio.py
Use --selftest --with-ocr separately for a real shipping-route smoke. These tests
use a deliberately wrong reader to prove that the app does not fabricate matches.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'apps/captcha-studio'
sys.path.insert(0, str(APP))
import engine as E
# Explicit module loader avoids colliding with an unrelated installed `server`.
spec = importlib.util.spec_from_file_location('studio_server', APP/'server.py')
S = importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
spec2 = importlib.util.spec_from_file_location('studio_launcher', APP/'launcher.py')
L = importlib.util.module_from_spec(spec2);spec2.loader.exec_module(L)


def request(base, path, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    h = {'Content-Type': 'application/json'} if data is not None else {}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(base+path, data=data, headers=h), timeout=20) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class EngineTests(unittest.TestCase):
    def test_18_arms_and_repeatability(self):
        report = E.selftest()
        self.assertEqual(report['arms'], 18)
        self.assertTrue(report['deterministic'])
        self.assertFalse(report['accuracy_claim'])

    def test_each_selection_custom_label_and_repeatability(self):
        for family, severities in E.FAMILIES.items():
            for severity in severities:
                with self.subTest(family=family, severity=severity):
                    payload={'family':family,'severity':severity,'count':1,'seed':14,'text':'Amber 42'}
                    config, a = E.generate(payload);_, b = E.generate(payload)
                    self.assertEqual(a,b);self.assertEqual(a[0][1]['label'],'Amber 42')
                    self.assertTrue(a[0][0].startswith(b'\x89PNG'))
                    self.assertEqual(a[0][1]['sha256'],hashlib.sha256(a[0][0]).hexdigest())

    def test_changed_seed_changes_pixels(self):
        p={'family':'control','count':1,'text':'Amber 42','seed':1}
        _, a=E.generate(p);_,b=E.generate({**p,'seed':2})
        self.assertNotEqual(a[0][0],b[0][0])

    def test_sample_index_replay(self):
        p={'family':'sampler','severity':'mixed','count':6,'seed':53}
        _, batch=E.generate(p)
        _, item=E.generate({**p,'count':1,'start_index':4})
        self.assertEqual(batch[4],item[0])

    def test_invalid_input_is_rejected(self):
        invalid=[{'count':0},{'count':33},{'count':True},{'seed':-1},{'seed':1.2},
                 {'seed':2147483648},{'family':'../../etc'}, {'text':'<script>'},
                 {'text':'x'*49},{'text':' hi'},{'text':'hi '},{'text':'\n'},
                 {'text':'è'},{'text':None},{'family':'control','severity':'extreme'},
                 {'start_index':-1},{'surprise':1}]
        for p in invalid:
            with self.subTest(payload=p),self.assertRaises(ValueError):E.generate(p)

    def test_manifest_export_and_reproducibility(self):
        _,items=E.generate({'family':'control','count':2,'text':'aB 42'})
        exported=E.export_zip(items);self.assertEqual(exported,E.export_zip(items))
        with zipfile.ZipFile(io.BytesIO(exported)) as z:
            rows=[json.loads(l) for l in z.read('manifest.jsonl').splitlines()]
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertEqual(row['label'],'aB 42')
                self.assertEqual(hashlib.sha256(z.read(row['image'])).hexdigest(),row['sha256'])
            self.assertTrue(all(not n.startswith('/') and '..' not in n for n in z.namelist()))
            self.assertIn('font_sha256',json.loads(z.read('provenance.json')))

    def test_duplicate_export_rejected(self):
        _,items=E.generate({'family':'control','count':1})
        with self.assertRaises(ValueError):E.export_zip(items*2)

    def test_no_case_or_whitespace_leniency(self):
        for got in ['amber','Amber ','Amber\n']:
            self.assertFalse(E.compare_result({'text':got},'Amber')['exact_match'])
        self.assertTrue(E.compare_result({'text':'Amber'},'Amber')['exact_match'])

    def test_font_tampering_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);expected=json.loads((E.FONT_DIR/'SHA256SUMS.json').read_text())
            (path/'SHA256SUMS.json').write_text(json.dumps(expected))
            (path/E.FONT_NAMES[0]).write_bytes(b'bad-font')
            with mock.patch.object(E,'FONT_DIR',path),self.assertRaises(RuntimeError):E.verify_fonts()
        E.verify_fonts()

    def test_no_system_font_dependency(self):
        fonts=E.G.available_fonts()
        self.assertEqual(len(fonts),8)
        self.assertTrue(all(Path(f).parent==E.FONT_DIR for f in fonts))

    def test_label_never_enters_reader(self):
        received=[]
        def fake(png):
            received.append(png)
            return {'text':'deliberately WRONG','raw_text':'deliberately WRONG','milliseconds':0,'route':'floor+lex'}
        studio=S.Studio(reader=fake)
        row=studio.create({'family':'control','count':1,'text':'Secret Label'})['items'][0]
        result=studio.read(row['id'])
        self.assertFalse(result['exact_match'])
        self.assertEqual(result['text'],'deliberately WRONG')
        self.assertEqual(result['expected'],'Secret Label')
        self.assertEqual(len(received),1)
        self.assertIsInstance(received[0],bytes)
        self.assertTrue(received[0].startswith(b'\x89PNG'))

    def test_cache_eviction_and_busy_are_explicit(self):
        studio=S.Studio(reader=lambda _: {'text':'x'})
        with mock.patch.object(S,'CACHE_LIMIT',1):
            batch=studio.create({'family':'control','count':2})
        with self.assertRaises(KeyError):studio.get(batch['items'][0]['id'])
        studio.ocr_lock.acquire()
        try:
            with self.assertRaises(BlockingIOError):studio.read(batch['items'][1]['id'])
        finally:studio.ocr_lock.release()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=S.Server(('127.0.0.1',0),S.Studio(reader=lambda _: {'text':'wrong','raw_text':'wrong','milliseconds':0,'route':'floor+lex'}))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)

    def test_health_and_static(self):
        for path in ['/','/app.js','/style.css','/api/health']:
            self.assertEqual(request(self.base,path)[0],200)
        info=json.loads(request(self.base,'/api/health')[1])
        self.assertTrue(info['ok']);self.assertEqual(info['build']['fonts'],8)
        self.assertFalse(info['build']['accuracy_target_met'])

    def test_generate_image_ocr_and_export(self):
        status,body,_=request(self.base,'/api/generate',{'family':'control','count':1,'text':'Amber'})
        self.assertEqual(status,200);row=json.loads(body)['items'][0]
        status,png,headers=request(self.base,row['url']);self.assertEqual(status,200)
        self.assertEqual(headers['Content-Type'],'image/png')
        status,body,_=request(self.base,'/api/ocr',{'id':row['id']})
        self.assertEqual(status,200);self.assertFalse(json.loads(body)['exact_match'])
        status,blob,headers=request(self.base,'/api/export',{'ids':[row['id']]})
        self.assertEqual(status,200);self.assertTrue(zipfile.is_zipfile(io.BytesIO(blob)))

    def test_label_hint_is_rejected(self):
        status,_,_=request(self.base,'/api/ocr',{'id':'a'*24,'label':'cheat'})
        self.assertEqual(status,400)

    def test_validation_and_expiration(self):
        self.assertEqual(request(self.base,'/api/generate',{'count':999})[0],400)
        self.assertEqual(request(self.base,'/api/ocr',{'id':'a'*24})[0],404)
        self.assertEqual(request(self.base,'/api/export',{'ids':['a'*24]})[0],404)
        self.assertEqual(request(self.base,'/../../uploads/secret')[0],404)
        self.assertEqual(request(self.base,'/api/app-download')[0],404)

    def test_same_origin_and_preview_host(self):
        self.assertEqual(request(self.base,'/api/generate',{'count':1},{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(request(self.base,'/api/generate',{'count':1},{'Origin':self.base})[0],200)
        self.assertEqual(request(self.base,'/api/generate',{'count':1},
            {'Host':'8488-test.e2b.app','Origin':'https://8488-test.e2b.app'})[0],200)

    def test_body_size_and_content_type(self):
        self.assertEqual(request(self.base,'/api/generate',{'text':'x'*20000})[0],413)
        self.assertEqual(request(self.base,'/api/generate',{}, {'Content-Type':'text/plain'})[0],415)


class LauncherTests(unittest.TestCase):
    def test_log_preserves_child_failure_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'studio.log'
            status=L.run_logged([sys.executable,'-c','import sys;print("forced selftest failure");sys.exit(7)'],log)
            self.assertEqual(status,7);self.assertIn('forced selftest failure',log.read_text())

    def test_failed_selftest_does_not_start_server(self):
        with mock.patch.object(sys,'argv',['launch.py','--no-install']),mock.patch.object(L,'available',return_value=True),mock.patch.object(L,'run_logged',return_value=7) as run:
            self.assertEqual(L.main(),7);self.assertEqual(run.call_count,1)
            self.assertIn('--selftest',run.call_args.args[0])

    def test_explicit_skip_and_restart_budget(self):
        with mock.patch.object(sys,'argv',['launch.py','--skip-selftest','--no-browser','--max-restarts','1']),mock.patch.object(L,'available',return_value=True),mock.patch.object(L,'run_logged',side_effect=[3,4]) as run,mock.patch.object(L.time,'sleep'):
            self.assertEqual(L.main(),4);self.assertEqual(run.call_count,2)
            self.assertNotIn('--selftest',run.call_args.args[0])

    def test_normal_exit_does_not_restart(self):
        with mock.patch.object(sys,'argv',['launch.py','--no-browser']),mock.patch.object(L,'available',return_value=True),mock.patch.object(L,'run_logged',side_effect=[0,0]) as run:
            self.assertEqual(L.main(),0);self.assertEqual(run.call_count,2)


class PackageTests(unittest.TestCase):
    def test_clean_room_package_and_missing_font_failure(self):
        spec=importlib.util.spec_from_file_location('studio_builder',ROOT/'tools/build_captcha_app_zip.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as tmp:
            result=builder.build(Path(tmp),allow_dirty=True)
            bundle=Path(result['directory'])
            with zipfile.ZipFile(result['zip']) as z:
                names=z.namelist()
                self.assertTrue(any(n.endswith('/start.bat') for n in names))
                self.assertFalse(any('/.git/' in n or '/data/' in n or 'credentials' in n for n in names))
                shell=next(i for i in z.infolist() if i.filename.endswith('/start.sh'))
                self.assertTrue((shell.external_attr >> 16) & 0o111)
            # Run from outside the bundle/source directories: no accidental import dependency.
            run=subprocess.run([sys.executable,str(bundle/'apps/captcha-studio/server.py'),'--selftest','--with-ocr'],cwd=tmp,capture_output=True,text=True,timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            report=json.loads(run.stdout)
            self.assertEqual(report['selftest'],'PASS')
            self.assertEqual(report['ocr_smoke']['route'],'floor+lex')
            self.assertFalse(report['accuracy_claim'])
            (bundle/'apps/captcha-studio/fonts'/E.FONT_NAMES[0]).write_bytes(b'corrupted')
            failed=subprocess.run([sys.executable,str(bundle/'apps/captcha-studio/server.py'),'--selftest'],cwd=tmp,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('Missing or changed bundled font',failed.stderr)

    def test_generation_leaves_core_files_unchanged(self):
        before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in E.CORE_FILES}
        E.generate({'family':'combined','severity':'mixed','count':3,'seed':82})
        after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in E.CORE_FILES}
        self.assertEqual(before,after)


if __name__=='__main__':
    unittest.main(verbosity=2)
