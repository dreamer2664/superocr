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

VERSION = "1.0.0"


def preflight(engine_path: str | None, quiet: bool = False) -> dict:
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
    rep["injection"] = injection_mod.backend_report()
    try:
        eng = engine_mod.ReaderEngine(engine_path) if engine_path else engine_mod.ReaderEngine()
        rep["engine_root"] = str(eng.root)
        rep["fonts_visible"] = len(eng.fonts_used)
    except Exception as e:
        rep["engine_root"] = f"ERROR: {e}"
        rep["fonts_visible"] = 0
    if not quiet:
        print(json.dumps(rep, indent=2))
    problems = []
    if rep["tkinter"] == "MISSING":
        problems.append("tkinter missing (needed for the GUI; Debian/Ubuntu: apt install python3-tk)")
    if not rep["capture_backends"]:
        problems.append("no capture backend (pip install mss, or use an X11 session)")
    if rep["injection"]["click"] == "MISSING":
        problems.append("no input-injection backend (Linux: apt install xdotool, or pip install pynput)")
    if str(rep["engine_root"]).startswith("ERROR"):
        problems.append(str(rep["engine_root"]))
    rep["problems"] = problems
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", help="path to the superocr reader root (baseline.py + tools/)")
    ap.add_argument("--config", help="config file (default ~/.qcaptcha.json)")
    ap.add_argument("--interval", type=int, help="poll interval ms (overrides config)")
    ap.add_argument("--mode", choices=["paste", "type"], help="delivery mode (overrides config)")
    ap.add_argument("--check", action="store_true", help="print environment report and exit")
    ap.add_argument("--install-deps", action="store_true",
                    help="pip install --user -r requirements.txt (Pillow + numpy) and exit")
    ap.add_argument("--selftest", action="store_true", help="wiring + smoke read, no GUI")
    ap.add_argument("--selftest-n", type=int, default=6, help="selftest sample count")
    ap.add_argument("--once", action="store_true", help="one headless read of the calibrated region")
    ap.add_argument("--no-paste", action="store_true", help="with --once: read only, never inject")
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

    rep = preflight(args.engine, quiet=True)
    for p in rep["problems"]:
        if args.selftest or args.check or not (args.once and "tkinter" in p):
            print(f"preflight: {p}", file=sys.stderr)

    if args.check:
        print(json.dumps(rep, indent=2))
        return 0 if not rep["problems"] else 2

    from qcaptcha import config as config_mod
    from qcaptcha import engine as engine_mod

    try:
        eng = engine_mod.ReaderEngine(args.engine)
    except engine_mod.EngineError as e:
        print(f"fatal: {e}", file=sys.stderr)
        return 2

    if args.selftest:
        res = eng.selftest(n=args.selftest_n)
        res["preflight"] = {k: rep[k] for k in
                            ("python", "pillow", "numpy", "capture_backends", "engine_root")}
        print(json.dumps(res, indent=2))
        return 0

    try:
        cfg = config_mod.load(Path(args.config) if args.config else None)
    except ValueError as e:
        print(f"fatal: {e}", file=sys.stderr)
        return 2
    if args.interval:
        cfg["interval_ms"] = args.interval
    if args.mode:
        cfg["paste_mode"] = args.mode

    if args.once:
        from qcaptcha.solver import Solver
        row = Solver(cfg, eng).read_once(deliver=not args.no_paste)
        print(json.dumps(row, indent=2))
        return 0 if row.get("error") is None else 3

    # GUI
    import tkinter as tk
    from qcaptcha.overlay import SolverApp
    from qcaptcha.solver import Solver

    root = tk.Tk()
    root.withdraw()
    SolverApp(cfg, eng, root=root, config_path=Path(args.config) if args.config else None,
              solver=Solver(cfg, eng))
    root.deiconify()
    print("qcaptcha running — panel on screen. F9 arm · F10 read once · F11 calibrate.")
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
