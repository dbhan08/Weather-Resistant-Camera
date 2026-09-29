"""Cut labelled 30x30 patches from the RaindropsOnWindshield dataset.

Dataset: Soboleva & Shipitko, arXiv:2104.05078, CC BY 4.0.
    pip install zenodo_get
    zenodo_get https://zenodo.org/record/4680442 --output-dir data/RaindropsOnWindshield

Layout (after unzip): image sequences with a matching binary mask per
frame, white = raindrop.  This script walks the tree, pairs each image with
its mask by stem, and samples patches:

    raindrop      mask coverage >= --pos-cover  (default 0.30)
    non_raindrop  mask coverage == 0 in the patch AND in a 1-patch margin,
                  so borderline drops never leak into negatives

Patches go to <out>/{raindrop,non_raindrop}/*.png so both Keras
`image_dataset_from_directory` and the tflite representative-dataset
loader can read them.  A `split.json` records which *sequences* went to
train / val / test, so frames from one clip never appear on both sides.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image

PATCH = 30
IMG_EXT = {".jpg", ".jpeg", ".png"}


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Pair image and mask files.  The dataset keeps masks in a sibling
    folder named 'mask' or 'masks'; fall back to any same-stem PNG whose
    path contains 'mask'."""
    masks = {}
    for p in root.rglob("*.png"):
        if "mask" in str(p.parent).lower():
            masks[p.stem] = p
    pairs = []
    for p in root.rglob("*"):
        if p.suffix.lower() in IMG_EXT and "mask" not in str(p.parent).lower() and p.stem in masks:
            pairs.append((p, masks[p.stem]))
    return sorted(pairs)


def sequence_of(img: Path, root: Path) -> str:
    """Sequence id = first path component under the dataset root."""
    return img.relative_to(root).parts[0]


def sample_patches(img: np.ndarray, mask: np.ndarray, rng: random.Random, n_pos: int, n_neg: int, pos_cover: float):
    h, w = mask.shape
    pos, neg = [], []
    ys, xs = np.nonzero(mask)
    # positives: centre on random drop pixels
    for _ in range(n_pos * 4):
        if len(pos) >= n_pos or len(ys) == 0:
            break
        i = rng.randrange(len(ys))
        y0, x0 = int(ys[i]) - PATCH // 2, int(xs[i]) - PATCH // 2
        if y0 < 0 or x0 < 0 or y0 + PATCH > h or x0 + PATCH > w:
            continue
        if mask[y0 : y0 + PATCH, x0 : x0 + PATCH].mean() >= pos_cover:
            pos.append(img[y0 : y0 + PATCH, x0 : x0 + PATCH])
    # negatives: random, with a clean margin
    for _ in range(n_neg * 4):
        if len(neg) >= n_neg:
            break
        y0, x0 = rng.randrange(0, h - PATCH), rng.randrange(0, w - PATCH)
        m = mask[max(0, y0 - PATCH) : y0 + 2 * PATCH, max(0, x0 - PATCH) : x0 + 2 * PATCH]
        if m.max() == 0:
            neg.append(img[y0 : y0 + PATCH, x0 : x0 + PATCH])
    return pos, neg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="unzipped RaindropsOnWindshield folder")
    ap.add_argument("--out", default="data/patches")
    ap.add_argument("--per-frame", type=int, default=4, help="positives and negatives per frame")
    ap.add_argument("--pos-cover", type=float, default=0.30)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    root, out = Path(a.root), Path(a.out)
    pairs = find_pairs(root)
    if not pairs:
        raise SystemExit(f"no image/mask pairs under {root}")
    rng = random.Random(a.seed)
    seqs = sorted({sequence_of(p, root) for p, _ in pairs})
    rng.shuffle(seqs)
    n = len(seqs)
    split = {"train": seqs[: int(0.7 * n)], "val": seqs[int(0.7 * n) : int(0.85 * n)], "test": seqs[int(0.85 * n) :]}
    where = {s: k for k, v in split.items() for s in v}

    counts = {k: {"raindrop": 0, "non_raindrop": 0} for k in split}
    for img_p, mask_p in pairs:
        part = where[sequence_of(img_p, root)]
        img = np.asarray(Image.open(img_p).convert("RGB"))
        mask = (np.asarray(Image.open(mask_p).convert("L")) > 127).astype(np.uint8)
        pos, neg = sample_patches(img, mask, rng, a.per_frame, a.per_frame, a.pos_cover)
        for label, patches in (("raindrop", pos), ("non_raindrop", neg)):
            d = out / part / label
            d.mkdir(parents=True, exist_ok=True)
            for j, p in enumerate(patches):
                Image.fromarray(p).save(d / f"{img_p.stem}_{j}.png")
            counts[part][label] += len(patches)
    (out / "split.json").write_text(json.dumps({"sequences": split, "counts": counts}, indent=2))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
