"""Train LensSoilNet on synthetic (or real, if you have labels) tiles.

    python -m lens_soiling.train --backgrounds data/clean --epochs 15 --out runs/soilnet

Without --backgrounds, procedural scenes are used (good for a smoke test,
not for a deployable model).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from . import CLASSES
from .dataset import SyntheticTiles, load_backgrounds
from .model import LensSoilNet, count_macs, count_params


def confusion(pred: np.ndarray, true: np.ndarray, k: int = len(CLASSES)) -> np.ndarray:
    cm = np.zeros((k, k), dtype=np.int64)
    for p, t in zip(pred, true):
        cm[t, p] += 1
    return cm


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: str) -> dict:
    model.eval()
    preds, trues = [], []
    for x, y in loader:
        logits = model(x.to(device))
        preds.append(logits.argmax(1).cpu().numpy())
        trues.append(np.asarray(y))
    p, t = np.concatenate(preds), np.concatenate(trues)
    cm = confusion(p, t)
    per_class = (np.diag(cm) / np.maximum(cm.sum(1), 1)).tolist()
    return {"accuracy": float((p == t).mean()), "per_class_recall": per_class, "confusion": cm.tolist()}


def train(
    backgrounds_dir: str | None,
    out: Path,
    epochs: int = 10,
    n_train: int = 8000,
    n_val: int = 1000,
    batch: int = 64,
    lr: float = 3e-3,
    width: float = 1.0,
    seed: int = 0,
    workers: int = 0,
    device: str | None = None,
) -> dict:
    torch.manual_seed(seed)
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    bgs = load_backgrounds(backgrounds_dir)
    if backgrounds_dir and not bgs:
        raise SystemExit(f"no images found under {backgrounds_dir}")
    # hold out ~20% of backgrounds for validation so val tiles never share a scene
    if bgs:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(bgs))
        cut = max(1, len(bgs) // 5)
        val_bgs, tr_bgs = [bgs[i] for i in idx[:cut]], [bgs[i] for i in idx[cut:]] or [bgs[i] for i in idx]
    else:
        tr_bgs, val_bgs = None, None

    tr = SyntheticTiles(tr_bgs, n_train, seed=seed + 1, augment=True)
    va = SyntheticTiles(val_bgs, n_val, seed=seed + 2, augment=False)
    tl = DataLoader(tr, batch_size=batch, shuffle=True, num_workers=workers, drop_last=True)
    vl = DataLoader(va, batch_size=256, num_workers=workers)

    model = LensSoilNet(width=width).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * len(tl))
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)

    out.mkdir(parents=True, exist_ok=True)
    history, best = [], 0.0
    for ep in range(epochs):
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        for x, y in tl:
            x, y = x.to(device), torch.as_tensor(y).to(device)
            opt.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(y)
            n += len(y)
        ev = evaluate(model, vl, device)
        rec = {"epoch": ep + 1, "train_loss": tot / n, "val_acc": ev["accuracy"], "sec": time.time() - t0}
        history.append(rec)
        print(json.dumps(rec))
        if ev["accuracy"] >= best:
            best = ev["accuracy"]
            torch.save(model.state_dict(), out / "soilnet.pt")

    model.load_state_dict(torch.load(out / "soilnet.pt", map_location=device))
    final = evaluate(model, vl, device)
    summary = {
        "classes": list(CLASSES),
        "width": width,
        "params": count_params(model),
        "macs_per_tile": count_macs(model.cpu()),
        "backgrounds": len(bgs),
        "val_accuracy": final["accuracy"],
        "per_class_recall": dict(zip(CLASSES, final["per_class_recall"])),
        "confusion_rows_true_cols_pred": final["confusion"],
        "history": history,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backgrounds", default=None, help="folder of clean lens photos")
    ap.add_argument("--out", default="runs/soilnet")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--n-train", type=int, default=8000)
    ap.add_argument("--n-val", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--width", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    s = train(a.backgrounds, Path(a.out), a.epochs, a.n_train, a.n_val, a.batch, a.lr, a.width, a.seed, a.workers, a.device)
    print(f"val_accuracy={s['val_accuracy']:.4f} params={s['params']} macs={s['macs_per_tile']}")


if __name__ == "__main__":
    main()
