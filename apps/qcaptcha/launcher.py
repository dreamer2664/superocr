#!/usr/bin/env python3
"""qcaptcha launcher — preflight, selftest, headless once-read, or the GUI.

    python3 apps/qcaptcha/launcher.py                 # start the app (GUI)
    python3 apps/qcaptcha/launcher.py --selftest      # wiring + smoke read, no GUI
    python3 apps/qcaptcha/launcher.py --once          # one headless read of the
                                                      # calibrated region (needs
                                                      # display + config)
    python3 apps/qcaptcha/launcher.py --check         # environment report only

Exit codes: 0 ok, 2 environment/preflight failure, 3 runtime failure.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

VERSION = "1.3.0"


def preflight(engine_path: str | None, quiet: bool = False,
              keys_file: str | None = None, reader_backend: str = "gemini") -> dict:
    from qcaptcha import engine as engine_mod
    from qcaptcha import injection as injection_mod

    rep: dict = {"version": VERSION, "python": sys.version.split()[0]}

    def probe(name, fn):
        try:
            rep[name] = fn()
        except Exception as e:
            rep[name] = f"ERROR: {e}"

    probe("pillow", lambda: __import__("PIL").__version__)
    probe("numpy", lambda: __import__("numpy").__version__)
    import importlib.util
    rep["tkinter"] = ("available" if importlib.util.find_spec("tkinter") else "MISSING")
    from qcaptcha import capture as capture_mod
    rep["capture_backends"] = capture_mod.available_backends()

    def _capture_probe():
        img = capture_mod.grab([0, 0, 120, 60])
        return f"ok {img.width}x{img.height}"

    probe("capture_test", _capture_probe)
    rep["injection"] = injection_mod.backend_report()
    try:
        eng = engine_mod.ReaderEngine(engine_path) if engine_path else engine_mod.ReaderEngine()
        rep["engine_root"] = str(eng.root)
        rep["fonts_visible"] = len(eng.fonts_used)
    except Exception as e:
        rep["engine_root"] = f"ERROR: {e}"
        rep["fonts_visible"] = 0
    from qcaptcha import gemini as gemini_mod
    try:
        keys = gemini_mod.load_keys(keys_file)
        rep["gemini_keys"] = len(keys)
        rep["gemini_keys_masked"] = [gemini_mod.mask(k) for k in keys[:3]]
    except Exception as e:
        rep["gemini_keys"] = f"ERROR: {e}"
    if not quiet:
        print(json.dumps(rep, indent=2))
    problems = []
    warnings = []
    if rep["tkinter"] == "MISSING":
        problems.append("tkinter missing (needed for the GUI; Debian/Ubuntu: apt install python3-tk)")
    if not rep["capture_backends"]:
        problems.append("no capture backend (pip install mss, or use an X11 session)")
    if rep["injection"]["click"] == "MISSING":
        problems.append("no input-injection backend (Linux: apt install xdotool, or pip install pynput)")
    if str(rep["engine_root"]).startswith("ERROR") and reader_backend == "local":
        problems.append(str(rep["engine_root"]))
    if reader_backend == "gemini" and not rep.get("gemini_keys"):
        warnings.append("no Gemini keys found — press Keys… in the app, or create "
                        "~/.qcaptcha-keys.json (the offline local reader is the fallback)")
    if not rep.get("capture_test", "").startswith("ok"):
        warnings.append(f"live capture test: {str(rep.get('capture_test'))[:90]}")
    rep["problems"] = problems
    rep["warnings"] = warnings
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", help="path to the superocr reader root (baseline.py + tools/)")
    ap.add_argument("--config", help="config file (default ~/.qcaptcha.json)")
    ap.add_argument("--reader", choices=["gemini", "local"],
                    help="reading backend (default: from config, else gemini)")
    ap.add_argument("--keys-file", help="Gemini keys file (default ~/.qcaptcha-keys.json)")
    ap.add_argument("--model", help="Gemini model id (default gemini-3-flash-preview)")
    ap.add_argument("--detect", action="store_true",
                    help="one live auto-calibration pass: capture screen, ask Gemini for "
                         "the captcha/text-box boxes, print them and exit")
    ap.add_argument("--interval", type=int, help="poll interval ms (overrides config)")
    ap.add_argument("--mode", choices=["paste", "type"], help="delivery mode (overrides config)")
    ap.add_argument("--check", action="store_true", help="print environment report and exit")
    ap.add_argument("--install-deps", action="store_true",
                    help="pip install --user -r requirements.txt (Pillow + numpy) and exit")
    ap.add_argument("--selftest", action="store_true", help="wiring + smoke read, no GUI")
    ap.add_argument("--selftest-n", type=int, default=6, help="selftest sample count")
    ap.add_argument("--once", action="store_true",
                    help="one headless solve: find the captcha + read + type (needs no "
                         "calibration when the reader can detect regions, i.e. Gemini)")
    ap.add_argument("--no-paste", action="store_true", help="with --once: read only, never inject")
    ap.add_argument("--phone-check", action="store_true",
                    help="report ADB + device + screencap + UI-dump health (JSON). "
                         "Start here for anything phone-related")
    ap.add_argument("--phone-study", action="store_true",
                    help="capture the phone's current screen + widget tree into a "
                         "study folder (screenshot, ui.xml, study.json, REPORT.md); "
                         "types nothing")
    ap.add_argument("--study-dir", default="qcaptcha-phone-study",
                    help="where --phone-study writes (default ./qcaptcha-phone-study)")
    ap.add_argument("--no-shot", action="store_true",
                    help="--phone-study: do not save screenshot.png (privacy)")
    ap.add_argument("--phone-once", action="store_true",
                    help="solve ONE captcha on the phone (read-only unless --phone-type)")
    ap.add_argument("--phone-type", action="store_true",
                    help="with --phone-once: tap the field and type the answer")
    ap.add_argument("--phone-arm", action="store_true",
                    help="watch the phone: solve and TYPE every new captcha as it "
                         "appears (Ctrl-C to stop)")
    ap.add_argument("--adb", default=None, help="path to the adb executable")
    ap.add_argument("--serial", default=None,
                    help="device serial (needed only when several are connected)")
    ap.add_argument("--type-test", dest="type_test", action="store_true",
                    help="click the calibrated text box and TYPE a test string — proves "
                         "that this machine can deliver keystrokes (no clipboard)")
    ap.add_argument("--version", action="version", version=f"qcaptcha {VERSION}")
    args = ap.parse_args(argv)

    # Friendly missing-dependency path — BEFORE importing anything PIL/numpy.
    missing = [mod for mod in ("PIL", "numpy") if importlib.util.find_spec(mod) is None]
    if missing:
        req = APP_DIR / "requirements.txt"
        cmd = [sys.executable, "-m", "pip", "install", "--user", "-r", str(req)]
        if args.install_deps:
            print("installing: " + " ".join(cmd))
            rc = subprocess.call(cmd)
            if rc != 0:
                print("pip failed — run it yourself and read the error:\n  "
                      + " ".join(cmd), file=sys.stderr)
                return 2
            missing = [m for m in ("PIL", "numpy") if importlib.util.find_spec(m) is None]
            if not missing:
                print("dependencies installed — re-run the launcher.")
                return 0
        print("missing Python packages: " + ", ".join(missing), file=sys.stderr)
        print("install them with:\n  " + " ".join(cmd), file=sys.stderr)
        print("(or re-run with --install-deps)", file=sys.stderr)
        return 2

    rep = preflight(args.engine, quiet=True, keys_file=args.keys_file,
                    reader_backend=args.reader or "gemini")
    for p in rep["problems"]:
        if args.selftest or args.check or not (args.once and "tkinter" in p):
            print(f"preflight: {p}", file=sys.stderr)
    for w in rep.get("warnings", []):
        if args.selftest or args.check:
            print(f"preflight warning: {w}", file=sys.stderr)

    if args.check:
        print(json.dumps(rep, indent=2))
        return 0 if not rep["problems"] else 2

    if args.detect:
        from qcaptcha import capture as capture_mod
        from qcaptcha import gemini as gemini_mod
        try:
            cl = gemini_mod.GeminiClient(keys_file=args.keys_file or None,
                                         models=[args.model] if args.model else None)
            shot = capture_mod.grab_full()
            print(f"screenshot {shot.width}x{shot.height} — asking Gemini…", file=sys.stderr)
            boxes = gemini_mod.detect_regions(cl, shot)
            print(json.dumps(boxes, indent=2))
            return 0 if any(boxes.values()) else 3
        except Exception as e:
            print(f"detect failed: {e}", file=sys.stderr)
            return 2

    from qcaptcha import config as config_mod
    from qcaptcha import engine as engine_mod

    # engine is needed for local reading, the generator (selftest) and lex cleanup
    eng = None
    try:
        eng = engine_mod.ReaderEngine(args.engine)
    except engine_mod.EngineError as e:
        if (args.reader or "gemini") == "local" or args.selftest:
            print(f"fatal: {e}", file=sys.stderr)
            return 2

    try:
        cfg = config_mod.load(Path(args.config) if args.config else None)
    except ValueError as e:
        print(f"fatal: {e}", file=sys.stderr)
        return 2
    if args.reader:
        cfg["reader_backend"] = args.reader
    if args.keys_file:
        cfg["gemini_keys_file"] = args.keys_file
    if args.model:
        cfg["gemini_model"] = args.model
    if args.interval:
        cfg["interval_ms"] = args.interval
    if args.mode:
        cfg["paste_mode"] = args.mode

    from qcaptcha import readers as readers_mod
    try:
        reader, note = readers_mod.make_reader(cfg, eng)
    except Exception as e:
        print(f"fatal: cannot build reader: {e}", file=sys.stderr)
        return 2
    if note:
        print(f"note: {note}", file=sys.stderr)

    if args.phone_check or args.phone_study or args.phone_once or args.phone_arm:
        from qcaptcha import phone as phone_mod
        adb = phone_mod.Adb(adb=args.adb or cfg.get("phone_adb") or None,
                            serial=args.serial or cfg.get("phone_serial") or None)
        if args.phone_check:
            rep = phone_mod.check(adb)
            print(json.dumps(rep, indent=2))
            return 0 if rep.get("ok") else 3
        if args.phone_study:
            info = phone_mod.study(adb, args.study_dir, shot=not args.no_shot)
            print(json.dumps(info, indent=2))
            print(f"study written to {info['dir']}/ — REPORT.md + study.json are "
                  f"safe to share; screenshot.png is your call.", file=sys.stderr)
            return 0
        client = getattr(reader, "client", None)
        solver = phone_mod.PhoneSolver(cfg, adb, reader, client=client)
        if args.phone_once:
            row = solver.solve_once(type_it=args.phone_type)
            print(json.dumps(row, indent=2))
            return 0 if row.get("error") is None else 3
        print("phone watch armed — solving + typing each new captcha. Ctrl-C stops.",
              file=sys.stderr)
        try:
            solver.run_loop(lambda r: print(json.dumps(r, default=str), flush=True))
        except KeyboardInterrupt:
            pass
        return 0

    if args.selftest:
        if reader.backend == "gemini":
            rows, ok = [], 0
            for i in range(args.selftest_n):
                img, label = eng.generate_sample(90210 + i)
                r = reader.read_with_retry(img, retry_upscale=False)
                hit = r["text"] == label
                ok += hit
                rows.append({"i": i, "want": label, "got": r["text"],
                             "seconds": r.get("seconds"), "exact": hit})
            res = {"backend": "gemini", "items": rows, "exact": ok, "n": args.selftest_n,
                   "note": "SMOKE (in-distribution, small n, network) — not a benchmark"}
        else:
            res = eng.selftest(n=args.selftest_n)
            res["backend"] = "local"
        res["preflight"] = {k: rep.get(k) for k in
                            ("python", "pillow", "numpy", "capture_backends", "engine_root",
                             "gemini_keys")}
        print(json.dumps(res, indent=2))
        return 0

    if args.type_test:
        from qcaptcha import injection as injection_mod
        t_reg = cfg.get("target_region")
        if not t_reg:
            print(json.dumps({"ok": False,
                              "error": "no text box calibrated — run Auto (Gemini) or "
                                       "Calibrate first, or pass a config with target_region"}))
            return 1
        print(json.dumps({"info": "focus the window with the text box… typing in 3 s"}),
              file=sys.stderr)
        import time as _t
        _t.sleep(3.0)
        try:
            info = injection_mod.focus_and_type(str(cfg.get("type_test_text", "qcaptcha test 123")),
                                                t_reg)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)[:200]}))
            return 1
        print(json.dumps(info, indent=2))
        return 0

    if args.once:
        from qcaptcha.solver import Solver
        row = Solver(cfg, reader).read_once(deliver=not args.no_paste)
        print(json.dumps(row, indent=2))
        return 0 if row.get("error") is None else 3

    # GUI
    import tkinter as tk
    from qcaptcha import gemini as gemini_mod
    from qcaptcha.overlay import SolverApp
    from qcaptcha.solver import Solver

    client = getattr(reader, "client", None)
    if client is None:
        try:
            client = gemini_mod.GeminiClient(
                keys_file=cfg.get("gemini_keys_file") or None)
        except Exception:
            client = None

    root = tk.Tk()
    root.withdraw()
    SolverApp(cfg, eng, client=client, root=root,
              config_path=Path(args.config) if args.config else None,
              solver=Solver(cfg, reader), reader_note=note)
    root.deiconify()
    print("qcaptcha running — panel on screen. F9 arm · F10 read once · F11 calibrate.")
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
