"""Tile dataset for the soiling classifier.

Label rule (per tile): 0 = clean, 1 = water, 2 = ice.  A rendered tile is
kept as soiled only if the soiling mask covers >= ``min_cover`` of it, so
the labels match what a human would call "obstructed".

Backgrounds come from a folder of clean photos when one is given (any JPG /
PNG, e.g. frames grabbed from the FIT0701 camera on a dry day).  Without a
folder, procedurally generated scenes are used so the whole pipeline runs
in CI with zero downloads.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from . import CLASSES, TILE
from .synth import procedural_background, render_drops, render_frost

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def load_backgrounds(folder: str | Path | None, limit: int | None = None) -> list[np.ndarray]:
    if folder is None:
        return []
    paths = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in IMG_EXT)
    if limit:
        paths = paths[:limit]
    out = []
    for p in paths:
        with Image.open(p) as im:
            out.append(np.asarray(im.convert("RGB")))
    return out


def random_tile(img: np.ndarray, rng: np.random.Generator, tile: int = TILE) -> np.ndarray:
    h, w, _ = img.shape
    if h < tile or w < tile:
        img = np.asarray(Image.fromarray(img).resize((max(w, tile), max(h, tile))))
        h, w, _ = img.shape
    y = int(rng.integers(0, h - tile + 1))
    x = int(rng.integers(0, w - tile + 1))
    return img[y : y + tile, x : x + tile].copy()


def make_sample(
    bg: np.ndarray | None, label: int, rng: np.random.Generator, tile: int = TILE, min_cover: float = 0.08
) -> tuple[np.ndarray, int]:
    """Return (tile_uint8, label).  If soiling coverage is too low the label
    falls back to clean so training targets stay honest."""
    base = random_tile(bg, rng, tile) if bg is not None else procedural_background(tile, tile, rng)
    if label == 0:
        return base, 0
    if label == 1:
        img, mask = render_drops(base, rng)
    else:
        img, mask = render_frost(base, rng)
    if mask.mean() < min_cover:
        return img, 0
    return img, label


def photometric_jitter(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Brightness / contrast / colour jitter + sensor noise, in float32 0..255."""
    x = img.astype(np.float32)
    x = x * rng.uniform(0.7, 1.3) + rng.uniform(-25, 25)
    gain = rng.uniform(0.9, 1.1, size=3).astype(np.float32)
    x = x * gain[None, None, :]
    x += rng.normal(0, rng.uniform(0, 6), size=x.shape).astype(np.float32)
    if rng.random() < 0.5:
        x = x[:, ::-1]
    if rng.random() < 0.5:
        x = x[::-1, :]
    return np.clip(x, 0, 255)


def to_tensor(img: np.ndarray) -> torch.Tensor:
    """uint8/float HWC 0..255 -> float CHW in [-1, 1] (matches int8 export scale)."""
    x = np.ascontiguousarray(img, dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(x).permute(2, 0, 1)


class SyntheticTiles(Dataset):
    """Infinite-ish synthetic tile dataset, deterministic per (seed, index)."""

    def __init__(
        self,
        backgrounds: Sequence[np.ndarray] | None,
        n: int,
        seed: int = 0,
        tile: int = TILE,
        augment: bool = True,
        class_weights: Sequence[float] = (0.4, 0.3, 0.3),
    ):
        self.bgs = list(backgrounds) if backgrounds else []
        self.n, self.seed, self.tile, self.augment = n, seed, tile, augment
        self.class_p = np.asarray(class_weights, dtype=np.float64) / np.sum(class_weights)

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int) -> tuple[torch.Tensor, int]:
        rng = np.random.default_rng((self.seed << 32) + i)
        label = int(rng.choice(len(CLASSES), p=self.class_p))
        bg = self.bgs[int(rng.integers(len(self.bgs)))] if self.bgs else None
        img, label = make_sample(bg, label, rng, self.tile)
        if self.augment:
            img = photometric_jitter(img, rng)
        return to_tensor(img), label


def tile_frame(frame: np.ndarray, tile: int = TILE) -> tuple[torch.Tensor, tuple[int, int]]:
    """Cut an HxWx3 frame into a (rows*cols, 3, tile, tile) batch.  Edge
    remainders are dropped, like TiledSoilingNet's fixed grid."""
    h, w, _ = frame.shape
    rows, cols = h // tile, w // tile
    crop = frame[: rows * tile, : cols * tile]
    tiles = crop.reshape(rows, tile, cols, tile, 3).transpose(0, 2, 1, 3, 4).reshape(-1, tile, tile, 3)
    batch = torch.stack([to_tensor(t) for t in tiles])
    return batch, (rows, cols)
