import json, subprocess, sys, time
from pathlib import Path
ROOT = Path("/tmp/socr")
DATA = Path("/home/user/socr-data")
out = {}
for suite in ("easy", "hard"):
    man = [json.loads(l) for l in open(DATA/suite/"manifest.jsonl")]
    for row in man:
        img = DATA/suite/row["image"]
        t0=time.time()
        try:
            p = subprocess.run(["python3", "baseline.py", str(img)], cwd=ROOT,
                               capture_output=True, text=True, timeout=60)
            got = (p.stdout.strip().splitlines() or [""])[0] if p.returncode==0 else ""
            err = None if p.returncode==0 else f"rc={p.returncode}"
        except Exception as e:
            got, err = "", type(e).__name__
        out[row["id"]] = {"label": row["label"], "got": got, "family": row["family"],
                          "ms": int((time.time()-t0)*1000), "err": err}
json.dump(out, open("/tmp/floor-items.json","w"))
n=len(out); exact=sum(1 for v in out.values() if v["got"]==v["label"])
print(f"floor items: {n}, exact: {exact}")
e=[v for k,v in out.items() if k.startswith('easy')]; h=[v for k,v in out.items() if not k.startswith('easy')]
print("easy:", sum(1 for v in e if v['got']==v['label']), "/", len(e))
print("hard:", sum(1 for v in h if v['got']==v['label']), "/", len(h))
