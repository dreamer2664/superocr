#!/usr/bin/env python3
"""S54 C2c — bounded whole-word prototype (t-20261013-768c).

Preregistration: reports/s54-word-reader/c2c_protocol.md (published BEFORE
training). Read-time input is ONLY the jointly-normalised word crop (C1
contract); no oracle glyph positions. CNN -> per-x-position softmax ->
CTC. Numpy-only (no new deps).

Modes:
  --smoke     20 steps on 64 crops; asserts loss decreases + decode sanity
  --train     bounded run (see protocol caps; DEV early-stop)
  --eval      single pass on EVAL items 1600+ (never used for selection)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from readers.glyphcnn import char_to_index, index_to_char  # noqa: E402
from readers.segmentation import ink_mask  # noqa: E402
from lex_projection import fix_token  # noqa: E402
from s54_word_crops import word_groups, word_box, WORD_H, CTX_WORD  # noqa: E402

MAX_W = 256          # protocol: crop width cap
ALPHA = 62           # shipped glyph classes
BLANK = 62           # CTC blank index
NOUT = ALPHA + 1     # 63
PAD_BIAS = 50.0      # force blank at padded t positions

SPLITS = {"train": (0, 1400), "dev": (1400, 1600), "eval": (1600, 2000)}


# ---------------------------------------------------------------- data
def build_split(corpus: Path, rows, lo, hi, cache: Path):
    if cache.is_file():
        d = np.load(cache, allow_pickle=True)
        return list(d["crops"]), list(d["labels"]), list(d["fams"])
    crops, labels, fams = [], [], []
    for r in rows[lo:hi]:
        img = Image.open(corpus / r["image"])
        mask = ink_mask(img)
        H, W = mask.shape
        fam = ("combined" if r["id"].startswith("combined")
               else f"{r['degradation_type']}/{r['severity']}")
        for wlabel, wboxes in word_groups(r["label"], r["char_boxes"]):
            x0, x1, y0, y1 = word_box(wboxes, W, H)
            crop = mask[y0:y1 + 1, x0:x1 + 1]
            if not crop.any():
                continue
            im = Image.fromarray((crop * 255).astype(np.uint8), "L")
            w2 = min(MAX_W, max(1, round(im.width * WORD_H / im.height)))
            im = im.resize((w2, WORD_H), Image.BILINEAR)
            arr = np.asarray(im, dtype=np.float32) / 255.0
            crops.append(arr)
            labels.append(np.array([char_to_index(c) for c in wlabel],
                                   dtype=np.int32))
            fams.append(fam)
    cc = np.empty(len(crops), dtype=object)
    for i, c in enumerate(crops):
        cc[i] = c
    ll = np.empty(len(labels), dtype=object)
    for i, l in enumerate(labels):
        ll[i] = l
    np.savez_compressed(cache, crops=cc, labels=ll,
                        fams=np.array(fams))
    return crops, labels, fams


# ------------------------------------------------------- conv machinery
def im2col(x, kh, kw):  # x (N,C,H,W) -> (N, C*kh*kw, OH*OW), same padding
    N, C, H, W = x.shape
    xp = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
    OH, OW = H, W
    cols = np.empty((N, C, kh, kw, OH, OW), dtype=x.dtype)
    for i in range(kh):
        for j in range(kw):
            cols[:, :, i, j] = xp[:, :, i:i + OH, j:j + OW]
    return cols.reshape(N, C * kh * kw, OH * OW)


def col2im(cols, x_shape):
    N, C, H, W = x_shape
    kh = kw = 3
    cols = cols.reshape(N, C, kh, kw, H, W)
    xp = np.zeros((N, C, H + 2, W + 2), dtype=cols.dtype)
    for i in range(kh):
        for j in range(kw):
            xp[:, :, i:i + H, j:j + W] += cols[:, :, i, j]
    return xp[:, :, 1:H + 1, 1:W + 1]


class Conv3:
    def __init__(self, cin, cout, rng):
        k = (3 * 3 * cin) ** -0.5
        self.W = rng.uniform(-k, k, (cout, cin * 9)).astype(np.float32)
        self.b = np.zeros(cout, dtype=np.float32)
        self.mW = np.zeros_like(self.W); self.vW = np.zeros_like(self.W)
        self.mb = np.zeros_like(self.b); self.vb = np.zeros_like(self.b)

    def fwd(self, x):
        self.x_shape = x.shape
        self.cols = im2col(x, 3, 3)
        N = x.shape[0]
        out = np.einsum('fk,nkp->nfp', self.W, self.cols,
                        optimize=True).reshape(N, self.W.shape[0],
                                               x.shape[2], x.shape[3])
        return out + self.b[None, :, None, None]

    def bwd(self, dout):
        N, F, H, W = dout.shape
        dout = dout.reshape(N, F, H * W)
        gW = np.einsum('nfp,nkp->fk', dout, self.cols, optimize=True)
        gb = dout.sum(axis=(0, 2))
        dcols = np.einsum('fc,nfp->ncp', self.W, dout, optimize=True)
        dx = col2im(dcols, self.x_shape)
        self.dW, self.db = gW.reshape(self.W.shape), gb
        return dx


class MaxPool:
    def __init__(self, ph, pw):
        self.ph, self.pw = ph, pw

    def fwd(self, x):
        N, C, H, W = x.shape
        Ho, Wo = H // self.ph, W // self.pw
        self.x_shape = x.shape
        xr = x[:, :, :Ho * self.ph, :Wo * self.pw].reshape(
            N, C, Ho, self.ph, Wo, self.pw).transpose(0, 1, 2, 4, 3, 5)
        flat = xr.reshape(N, C, Ho, Wo, self.ph * self.pw)
        self.arg = flat.argmax(axis=-1)          # (N,C,Ho,Wo)
        self.Ho, self.Wo = Ho, Wo
        return np.take_along_axis(flat, self.arg[..., None], axis=-1)[..., 0]

    def bwd(self, dout):
        N, C, _, _ = self.x_shape
        dx = np.zeros(self.x_shape, dtype=np.float32)
        dxr = dx[:, :, :self.Ho * self.ph, :self.Wo * self.pw].reshape(
            N, C, self.Ho, self.ph, self.Wo, self.pw)
        for flat in range(self.ph * self.pw):
            i, j = divmod(flat, self.pw)
            dxr[:, :, :, i, :, j] += dout * (self.arg == flat)
        return dx


class ReLU:
    def fwd(self, x):
        self.mask = x > 0
        return x * self.mask

    def bwd(self, dout):
        return dout * self.mask


class WordCTCNet:
    """32xW -> conv/pool stack -> per-x features -> linear -> 63 logits."""

    def __init__(self, rng):
        self.c1 = Conv3(1, 8, rng)
        self.p1 = MaxPool(2, 2)
        self.c2 = Conv3(8, 16, rng)
        self.p2 = MaxPool(2, 1)
        self.c3 = Conv3(16, 32, rng)
        self.p3 = MaxPool(2, 1)
        self.r1, self.r2, self.r3 = ReLU(), ReLU(), ReLU()
        k = (32 * 4) ** -0.5
        self.Wo = rng.uniform(-k, k, (128, NOUT)).astype(np.float32)
        self.bo = np.zeros(NOUT, dtype=np.float32)
        self.mWo = np.zeros_like(self.Wo); self.vWo = np.zeros_like(self.Wo)
        self.mbo = np.zeros_like(self.bo); self.vbo = np.zeros_like(self.bo)
        self.t = 0

    def params(self):
        return [(self.c1.W, self.c1), (self.c1.b, self.c1),
                (self.c2.W, self.c2), (self.c2.b, self.c2),
                (self.c3.W, self.c3), (self.c3.b, self.c3),
                (self.Wo, self), (self.bo, self)]

    def forward(self, x):
        """x (N,1,32,W even). Returns logits (N, W//2, NOUT)."""
        self.x_shape = x.shape
        h = self.r1.fwd(self.c1.fwd(x)); h = self.p1.fwd(h)
        h = self.r2.fwd(self.c2.fwd(h)); h = self.p2.fwd(h)
        h = self.r3.fwd(self.c3.fwd(h)); h = self.p3.fwd(h)
        N, C, H4, T = h.shape
        assert H4 == 4, H4
        self.h = h
        feats = h.transpose(0, 3, 1, 2).reshape(N, T, 128)
        self.feats = feats
        logits = feats @ self.Wo + self.bo
        return logits

    def backward(self, dlogits):
        N, T, _ = dlogits.shape
        self.dWo = np.einsum('ntp,ntq->pq', self.feats, dlogits,
                             optimize=True)
        self.dbo = dlogits.sum(axis=(0, 1))
        dfeats = dlogits @ self.Wo.T
        dh = dfeats.reshape(N, T, 32, 4).transpose(0, 2, 3, 1)
        dh = self.p3.bwd(dh); dh = self.r3.bwd(dh); dh = self.c3.bwd(dh)
        dh = self.p2.bwd(dh); dh = self.r2.bwd(dh); dh = self.c2.bwd(dh)
        dh = self.p1.bwd(dh); dh = self.r1.bwd(dh); dh = self.c1.bwd(dh)
        return dh

    def adam(self, lr=1e-3, betas=(0.9, 0.999), eps=1e-8):
        self.t += 1
        b1, b2 = betas
        entries = [(self.c1, 'dW', 'W', 'mW', 'vW'),
                   (self.c1, 'db', 'b', 'mb', 'vb'),
                   (self.c2, 'dW', 'W', 'mW', 'vW'),
                   (self.c2, 'db', 'b', 'mb', 'vb'),
                   (self.c3, 'dW', 'W', 'mW', 'vW'),
                   (self.c3, 'db', 'b', 'mb', 'vb')]
        for obj, dgk, gk, mk, vk in entries:
            g, p = getattr(obj, dgk), getattr(obj, gk)
            m, v = getattr(obj, mk), getattr(obj, vk)
            m *= b1; m += (1 - b1) * g
            v *= b2; v += (1 - b2) * g * g
            mh = m / (1 - b1 ** self.t); vh = v / (1 - b2 ** self.t)
            p -= lr * mh / (np.sqrt(vh) + eps)
        for gk, pk, mk, vk in [('dWo', 'Wo', 'mWo', 'vWo'),
                               ('dbo', 'bo', 'mbo', 'vbo')]:
            g, p = getattr(self, gk), getattr(self, pk)
            m, v = getattr(self, mk), getattr(self, vk)
            m *= b1; m += (1 - b1) * g
            v *= b2; v += (1 - b2) * g * g
            mh = m / (1 - b1 ** self.t); vh = v / (1 - b2 ** self.t)
            p -= lr * mh / (np.sqrt(vh) + eps)


# ---------------------------------------------------------------- CTC
def ctc_loss_grad(logits, labels, t_valid):
    """Scaled forward-backward CTC. logits (T,NOUT) float64, labels (L,).
    Returns loss, dlogits (T,NOUT)."""
    T, _ = logits.shape
    L = len(labels)
    S = 2 * L + 1
    if T < L:  # cannot align; zero grad, huge loss
        return 1e6, np.zeros_like(logits)
    ext = np.full(S, BLANK, dtype=np.int64)
    ext[1::2] = labels
    logp = logits - logits.max(axis=1, keepdims=True)
    p = np.exp(logp); p /= p.sum(axis=1, keepdims=True)

    alpha = np.zeros((T, S)); beta = np.zeros((T, S))
    cs = np.zeros(T)  # scale factors
    alpha[0, 0] = p[0, BLANK]
    if S > 1:
        alpha[0, 1] = p[0, ext[1]]
    cs[0] = alpha[0].sum(); alpha[0] /= cs[0]
    for t in range(1, T):
        a = alpha[t - 1].copy()
        a[1:] += alpha[t - 1][:-1]
        a[2:] += np.where(ext[2:] != ext[:-2], alpha[t - 1][:-2], 0.0)
        alpha[t] = a * p[t, ext]
        cs[t] = alpha[t].sum()
        if cs[t] > 0:
            alpha[t] /= cs[t]
    beta[T - 1] = 0.0
    beta[T - 1, S - 1] = 1.0
    beta[T - 1, S - 2] = 1.0
    for t in range(T - 2, -1, -1):
        pn = p[t + 1]                     # emission probs at t+1
        b = beta[t + 1] * pn[ext]         # stay: s -> s
        b[:-1] += beta[t + 1][1:] * pn[ext[1:]]      # s -> s+1
        b[:-2] += np.where(ext[2:] != ext[:-2],
                           beta[t + 1][2:] * pn[ext[2:]], 0.0)  # s -> s+2
        beta[t] = b
        s = beta[t].sum()
        if s > 0:
            beta[t] /= s
    ll = np.log(cs).sum() + np.log(alpha[T - 1, S - 1] + alpha[T - 1, S - 2])
    # posterior marginals gamma_t(k) = sum_{s: ext[s]=k} alpha*beta / (prod cs)
    ab = alpha * beta
    post = np.zeros((T, NOUT))
    np.add.at(post, (np.arange(T)[:, None], ext[None, :]), ab)
    post /= np.maximum(post.sum(axis=1, keepdims=True), 1e-30)
    loss = -ll
    dlogits = (p - post) * (t_valid[:, None] > 0)
    return loss, dlogits


def apply_pad_bias(logits, t_valid):
    """Force blank probability ~1 at padded positions (train + decode)."""
    lg = logits.copy()
    pad = t_valid == 0
    if pad.any():
        lg[pad, :] = 0.0
        lg[pad, BLANK] = PAD_BIAS
    return lg


def greedy_decode(logits, t_valid):
    lg = apply_pad_bias(logits, t_valid)
    idx = lg.argmax(axis=1)
    out, prev = [], BLANK
    for i in idx[:int(t_valid.sum())]:
        if i != prev and i != BLANK:
            out.append(i)
        prev = i
    return "".join(index_to_char(i) for i in out)


def make_batch(crops, labels, idxs):
    ws = [crops[i].shape[1] for i in idxs]
    Wm = max(ws)
    Wm += Wm % 2
    N = len(idxs)
    x = np.zeros((N, 1, WORD_H, Wm), dtype=np.float32)
    tv = np.zeros((N, Wm // 2))
    for n, i in enumerate(idxs):
        c = crops[i]
        x[n, 0, :, :c.shape[1]] = c
        tv[n, :max(1, (c.shape[1] + 1) // 2)] = 1
    return x, tv


def run_batch(net, crops, labels, idxs, train=True, lr=1e-3):
    x, tv = make_batch(crops, labels, idxs)
    logits = net.forward(x)
    N, T, _ = logits.shape
    losses, dlogits = [], np.zeros_like(logits, dtype=np.float64)
    for n, i in enumerate(idxs):
        lg = apply_pad_bias(logits[n].astype(np.float64), tv[n])
        l, g = ctc_loss_grad(lg, labels[i], tv[n])
        losses.append(l)
        dlogits[n] = g
    if train:
        net.backward(dlogits.astype(np.float32))
        net.adam(lr=lr)
    return float(np.mean(losses)), logits, tv


def eval_split(net, crops, labels, fams, idxs):
    from collections import defaultdict
    per = defaultdict(lambda: [0, 0, 0, 0])  # n, exact, lex, lexci
    for s in range(0, len(idxs), 32):
        chunk = idxs[s:s + 32]
        x, tv = make_batch(crops, labels, chunk)
        logits = net.forward(x)
        for n, i in enumerate(chunk):
            got = greedy_decode(logits[n].astype(np.float64), tv[n])
            lab = "".join(index_to_char(v) for v in labels[i])
            lexed = fix_token(got)
            f = per[fams[i]]
            f[0] += 1
            f[1] += got == lab
            f[2] += lexed == lab
            f[3] += lexed.lower() == lab.lower()
    tot = [sum(v) for v in zip(*per.values())]
    return per, tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hard2000")
    ap.add_argument("--mode", choices=["smoke", "train", "eval"],
                    required=True)
    ap.add_argument("--weights", default="models/s54-c2c-word-v0.npz")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--out", default="reports/s54-word-reader/c2c_result.json")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    rows = [json.loads(l) for l in open(corpus / "manifest.jsonl")]
    rng = np.random.default_rng(768)
    net = WordCTCNet(rng)

    if args.mode == "smoke":
        crops, labels, fams = build_split(corpus, rows, 0, 20,
                                          Path("/tmp/s54-c2c-smoke.npz"))
        print(f"smoke: {len(crops)} crops")
        idxs = list(range(min(64, len(crops))))
        first = None
        for step in range(20):
            loss, logits, tv = run_batch(net, crops, labels, idxs)
            if first is None:
                first = loss
            print(f"  step {step:2d} loss {loss:.4f}", flush=True)
        assert loss < first * 0.7, f"loss did not decrease: {first} -> {loss}"
        got = greedy_decode(logits[0].astype(np.float64), tv[0])
        lab = "".join(index_to_char(v) for v in labels[idxs[0]])
        print(f"  decode sample 0: {got!r} (label {lab!r})")
        print(f"SMOKE OK: loss {first:.4f} -> {loss:.4f}")
        return 0

    if args.mode == "train":
        tr = build_split(corpus, rows, *SPLITS["train"],
                         Path("/tmp/s54-c2c-train.npz"))
        dv = build_split(corpus, rows, *SPLITS["dev"],
                         Path("/tmp/s54-c2c-dev.npz"))
        crops, labels, _ = tr
        dcrops, dlabels, dfams = dv
        n = len(crops)
        print(f"train crops {n}, dev crops {len(dcrops)}")
        t0 = time.time()
        best = None
        for ep in range(args.epochs):
            order = rng.permutation(n)
            ep_loss = 0.0
            for s in range(0, n, 32):
                if (time.time() - t0) / 60 > args.max_minutes:
                    print(f"runtime cap hit at epoch {ep}")
                    args.epochs = ep
                    break
                chunk = order[s:s + 32]
                chunk = sorted(chunk, key=lambda i: crops[i].shape[1])
                loss, _, _ = run_batch(net, crops, labels, chunk, lr=args.lr)
                ep_loss += loss * len(chunk)
            per, tot = eval_split(net, dcrops, dlabels, dfams,
                                  list(range(len(dcrops))))
            print(f"epoch {ep}: train-loss {ep_loss / n:.4f} "
                  f"DEV word-exact {tot[1]}/{tot[0]} = {tot[1]/tot[0]:.3f} "
                  f"(+lex {tot[2]/tot[0]:.3f})", flush=True)
            if best is None or tot[2] >= best[0]:
                best = (tot[2], ep)
                save_net(net, args.weights)
            if (time.time() - t0) / 60 > args.max_minutes:
                break
        print(f"best DEV +lex {best[0]/max(1,tot[0]):.3f} @ epoch {best[1]}")
        return 0

    if args.mode == "eval":
        load_net(net, args.weights)
        ec = build_split(corpus, rows, *SPLITS["eval"],
                         Path("/tmp/s54-c2c-eval.npz"))
        crops, labels, fams = ec
        per, tot = eval_split(net, crops, labels, fams,
                              list(range(len(crops))))
        out = {"_TOTAL": {"words": tot[0], "word_exact": round(tot[1]/tot[0], 4),
                          "plus_lex": round(tot[2]/tot[0], 4),
                          "lex_ci": round(tot[3]/tot[0], 4)}}
        print(f"\n{'family':28s} {'n':>5s} {'exact':>7s} {'+lex':>7s} {'lexci':>7s}")
        for k in sorted(per):
            f = per[k]
            out[k] = {"words": f[0], "word_exact": round(f[1]/f[0], 4),
                      "plus_lex": round(f[2]/f[0], 4),
                      "lex_ci": round(f[3]/f[0], 4)}
            print(f"{k:28s} {f[0]:5d} {f[1]/f[0]:7.3f} {f[2]/f[0]:7.3f} "
                  f"{f[3]/f[0]:7.3f}")
        print(f"{'TOTAL':28s} {tot[0]:5d} {tot[1]/tot[0]:7.3f} "
              f"{tot[2]/tot[0]:7.3f} {tot[3]/tot[0]:7.3f}")
        out["_comparator"] = {"composed": 0.537, "composed_ci": 0.585,
                              "composed_plus_lex": 0.664, "lex_ci": 0.767}
        out["_bar"] = ("word_exact_plus_lex > 0.664 on EVAL, no family "
                       "-5pts vs composed+lex (c2c_protocol.md)")
        Path(args.out).write_text(json.dumps(out, indent=1))
        print(f"report {args.out}")
        return 0


def save_net(net, path):
    d = {"c1W": net.c1.W, "c1b": net.c1.b, "c2W": net.c2.W, "c2b": net.c2.b,
         "c3W": net.c3.W, "c3b": net.c3.b, "Wo": net.Wo, "bo": net.bo}
    np.savez(path, **d)


def load_net(net, path):
    d = np.load(path)
    net.c1.W[...] = d["c1W"]; net.c1.b[...] = d["c1b"]
    net.c2.W[...] = d["c2W"]; net.c2.b[...] = d["c2b"]
    net.c3.W[...] = d["c3W"]; net.c3.b[...] = d["c3b"]
    net.Wo[...] = d["Wo"]; net.bo[...] = d["bo"]


if __name__ == "__main__":
    raise SystemExit(main())
