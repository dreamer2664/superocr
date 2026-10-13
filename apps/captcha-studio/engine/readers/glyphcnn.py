#!/usr/bin/env python3
"""glyphcnn.py — a small from-scratch glyph CNN, in numpy (t-20261011-f0d2).

JOBS.md allows numpy + Pillow only, so there is no torch here: forward pass,
backward pass (im2col convolutions), Adam, save/load — all plain numpy, all
deterministic given a seed.

    input  24x24 grayscale glyph crop, ink bright
    conv1  3x3x1->8   + ReLU + 2x2 max-pool   ->  8x12x12
    conv2  3x3x8->16  + ReLU + 2x2 max-pool   -> 16x6x6
    dense  576 -> 96  + ReLU
    dense  96  -> 62  + softmax

62 classes: 0-9 A-Z a-z. ~62k parameters, so the weights are committed (the
recipe file records seed, data sizes and measured accuracy; see recipes/).
"""

from __future__ import annotations

import json
import numpy as np

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
N_CLASSES = len(CHARS)


def char_to_index(ch: str) -> int:
    return CHARS.index(ch)


def index_to_char(i: int) -> str:
    return CHARS[i]


# ---------------------------------------------------------------------------
# layers (forward + backward, all arrays float32)
# ---------------------------------------------------------------------------

def im2col(x: np.ndarray, kh: int, kw: int, pad: int) -> np.ndarray:
    n, c, h, w = x.shape
    xp = np.pad(x, ((0, 0), (0, 0), (pad, pad), (pad, pad)))
    cols = np.empty((n, c, h * w, kh * kw), dtype=x.dtype)
    for i in range(kh):
        for j in range(kw):
            cols[:, :, :, i * kw + j] = xp[:, :, i:i + h, j:j + w].reshape(n, c, h * w)
    # (n, c, HW, K) -> (n, HW, c*K): transpose BEFORE reshape, or the memory
    # order silently mixes channel, pixel and kernel indices. The forward pass
    # and dw stay mutually consistent when this is wrong (which is why only a
    # naive-convolution comparison catches it), but dx is garbage.
    return cols.transpose(0, 2, 1, 3).reshape(n, h * w, c * kh * kw)


def col2im(cols: np.ndarray, x_shape, kh: int, kw: int, pad: int) -> np.ndarray:
    n, c, h, w = x_shape
    cols = cols.reshape(n, h * w, c, kh * kw).transpose(0, 2, 1, 3)
    xp = np.zeros((n, c, h + 2 * pad, w + 2 * pad), dtype=cols.dtype)
    for i in range(kh):
        for j in range(kw):
            xp[:, :, i:i + h, j:j + w] += cols[:, :, :, i * kw + j].reshape(n, c, h, w)
    if pad == 0:
        return xp
    return xp[:, :, pad:-pad, pad:-pad]


def conv_forward(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    n, c, h, ww = x.shape
    o, _, kh, kw = w.shape
    cols = im2col(x, kh, kw, pad=kh // 2)                  # (N, HW, C*K*K)
    out = cols @ w.reshape(o, -1).T + b.reshape(1, o)      # (N, HW, O)
    return out.transpose(0, 2, 1).reshape(n, o, h, ww)


def conv_backward(x, w, dout):
    n, c, h, ww = x.shape
    o, _, kh, kw = w.shape
    dout2 = dout.reshape(n, o, h * ww).transpose(0, 2, 1)  # (N, HW, O)
    cols = im2col(x, kh, kw, pad=kh // 2)
    wf = w.reshape(o, -1)
    dw = (dout2.transpose(0, 1, 2).reshape(-1, o).T @ cols.reshape(-1, cols.shape[-1]))
    dw = dw.reshape(o, -1).reshape(w.shape)
    db = dout2.sum(axis=(0, 1))
    dcols = dout2 @ wf                                       # (N, HW, C*K*K)
    dx = col2im(dcols, x.shape, kh, kw, pad=kh // 2)
    return dx, dw.astype(x.dtype), db.astype(x.dtype)


def maxpool_forward(x: np.ndarray):
    n, c, h, w = x.shape
    xr = x.reshape(n, c, h // 2, 2, w // 2, 2)
    out = xr.max(axis=(3, 5))
    mask = (xr == out[:, :, :, None, :, None])
    return out, mask


def maxpool_backward(dout: np.ndarray, mask: np.ndarray, x_shape) -> np.ndarray:
    n, c, h, w = x_shape
    expanded = (mask * dout[:, :, :, None, :, None]).reshape(n, c, h, w)
    return expanded


def relu(x): return np.maximum(x, 0.0)
def relu_grad(x): return (x > 0).astype(x.dtype)


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------

class GlyphCNN:
    """Weights + forward/backward + Adam. Deterministic given the seed."""

    def __init__(self, seed: int = 0, init_from: dict | None = None,
                 width: tuple[int, int] = (8, 16), dense: int = 96,
                 input_hw: tuple[int, int] = (24, 24)):
        if init_from is not None:
            self.p = {k: np.array(v, dtype=np.float32) for k, v in init_from.items()}
            self.width = (self.p["w1"].shape[0], self.p["w2"].shape[0])
            self.dense = self.p["w3"].shape[1]
            flat = self.p["w3"].shape[0]
            self.input_hw = (int((flat / self.width[1]) ** 0.5) * 4, int((flat / self.width[1]) ** 0.5) * 4)
            return
        c1, c2 = width
        self.width, self.dense, self.input_hw = (c1, c2), dense, input_hw
        flat = c2 * (input_hw[0] // 4) * (input_hw[1] // 4)
        rng = np.random.default_rng(seed)
        t = lambda shape, fan_in: ((rng.standard_normal(shape) * np.sqrt(2.0 / fan_in))
                                   .astype(np.float32))
        self.p = {
            "w1": t((c1, 1, 3, 3), 9),          "b1": np.zeros(c1, dtype=np.float32),
            "w2": t((c2, c1, 3, 3), 9 * c1),    "b2": np.zeros(c2, dtype=np.float32),
            "w3": t((flat, dense), flat),       "b3": np.zeros(dense, dtype=np.float32),
            "w4": t((dense, N_CLASSES), dense), "b4": np.zeros(N_CLASSES, dtype=np.float32),
        }

    # -- forward: returns cache for backward -------------------------------
    def forward(self, x: np.ndarray):
        p = self.p
        z1 = conv_forward(x, p["w1"], p["b1"])
        a1 = relu(z1)
        p1, m1 = maxpool_forward(a1)                     # 8x12x12
        z2 = conv_forward(p1, p["w2"], p["b2"])
        a2 = relu(z2)
        p2, m2 = maxpool_forward(a2)                     # 16x6x6
        flat = p2.reshape(p2.shape[0], -1)               # 576
        z3 = flat @ p["w3"] + p["b3"]
        a3 = relu(z3)
        logits = a3 @ p["w4"] + p["b4"]
        probs = softmax(logits)
        cache = (x, z1, p1, m1, z2, p2, m2, flat, z3, a3, logits, probs)
        return probs, cache

    def loss_and_grads(self, x: np.ndarray, y: np.ndarray):
        """Mean softmax cross-entropy and its gradients (Adam-ready dict)."""
        probs, (x, z1, p1, m1, z2, p2, m2, flat, z3, a3, logits, _) = self.forward(x)
        n = x.shape[0]
        eps = 1e-9
        loss = float(-np.log(np.clip(probs[np.arange(n), y], eps, 1.0)).mean())
        dlogits = probs.copy()
        dlogits[np.arange(n), y] -= 1.0
        dlogits /= n
        g = {}
        g["w4"] = a3.T @ dlogits
        g["b4"] = dlogits.sum(axis=0)
        da3 = dlogits @ self.p["w4"].T
        dz3 = da3 * relu_grad(z3)
        g["w3"] = flat.T @ dz3
        g["b3"] = dz3.sum(axis=0)
        dflat = dz3 @ self.p["w3"].T
        dp2 = dflat.reshape(p2.shape)
        da2 = maxpool_backward(dp2, m2, z2.shape)
        dz2 = da2 * relu_grad(z2)
        dp1, g["w2"], g["b2"] = conv_backward(p1, self.p["w2"], dz2)
        da1 = maxpool_backward(dp1, m1, z1.shape)
        dz1 = da1 * relu_grad(z1)
        _, g["w1"], g["b1"] = conv_backward(x, self.p["w1"], dz1)
        # keep the dtype of the input: float64 training inputs must produce
        # float64 gradients, or a finite-difference check drowns in float32
        # rounding noise (learned the hard way - see tests/test_glyphcnn.py)
        return loss, {k: v.astype(x.dtype) for k, v in g.items()}

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.forward(x)[0].argmax(axis=1)

    # -- persistence -------------------------------------------------------
    def save(self, path: str):
        np.savez_compressed(path, **self.p)

    @classmethod
    def load(cls, path: str) -> "GlyphCNN":
        with np.load(path) as data:
            return cls(init_from={k: data[k] for k in data.files})

    # -- training ----------------------------------------------------------
    def fit(self, xtr, ytr, xva=None, yva=None, epochs: int = 8,
            batch: int = 128, lr: float = 2e-3, seed: int = 1, verbose=False,
            lr_end: float | None = 4e-4):
        """Adam with a cosine LR decay (lr -> lr_end).

        Returns the history as a list of (epoch, loss, val_acc|None).
        """
        rng = np.random.default_rng(seed)
        m = {k: np.zeros_like(v) for k, v in self.p.items()}
        v = {k: np.zeros_like(v) for k, v in self.p.items()}
        b1, b2, eps = 0.9, 0.999, 1e-8
        step = 0
        history = []
        steps_per_epoch = max(1, (len(xtr) + batch - 1) // batch)
        total_steps = steps_per_epoch * epochs
        for epoch in range(1, epochs + 1):
            order = rng.permutation(len(xtr))
            losses = []
            for start in range(0, len(order), batch):
                idx = order[start:start + batch]
                loss, g = self.loss_and_grads(xtr[idx], ytr[idx])
                losses.append(loss)
                step += 1
                frac = step / max(1, total_steps)
                cur_lr = (lr_end + 0.5 * (lr - lr_end) * (1 + np.cos(np.pi * frac))
                          if lr_end is not None else lr)
                for k in self.p:
                    m[k] = b1 * m[k] + (1 - b1) * g[k]
                    v[k] = b2 * v[k] + (1 - b2) * g[k] ** 2
                    mhat = m[k] / (1 - b1 ** step)
                    vhat = v[k] / (1 - b2 ** step)
                    self.p[k] -= (cur_lr * mhat / (np.sqrt(vhat) + eps)).astype(np.float32)
            val_acc = None
            if xva is not None and len(xva):
                val_acc = float((self.predict(xva) == yva).mean())
            history.append((epoch, float(np.mean(losses)), val_acc))
            if verbose:
                print(f"  epoch {epoch}: loss {np.mean(losses):.4f}"
                      + (f", val acc {val_acc:.3f}" if val_acc is not None else ""))
        return history


def recipe_path_from(weights_path: str) -> str:
    """models/foo.npz -> recipes/foo.json (kept next to the weights)."""
    return weights_path.replace("models/", "recipes/").replace(".npz", ".json")


def write_recipe(weights_path: str, info: dict):
    path = recipe_path_from(weights_path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path
