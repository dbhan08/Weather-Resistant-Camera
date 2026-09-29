"""Synthetic soiling renderers.

Two physical effects are rendered on top of a clean tile:

* ``render_drops``  -- adherent water drops.  A drop on a lens acts as a tiny
  fish-eye lens: inside the drop the scene appears minified, inverted and
  blurred, with a dark rim (total internal reflection at the edge) and a
  bright specular highlight.  This follows the adherent-raindrop model of
  You et al. (PAMI 2016) and the appearance used in Qian et al. (CVPR 2018).
* ``render_frost``  -- ice / frost.  Frost scatters light: the image is
  desaturated, blurred, pulled toward white and overlaid with a fractal
  crystal texture.  This is the "frost" corruption idea from ImageNet-C
  (Hendrycks & Dietterich, 2019), implemented procedurally so no frost
  photographs are required.

Everything is NumPy + PIL only, so it runs on the STM32 host PC and in CI.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def _to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def _blur(img: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return img.astype(np.float32)
    return np.asarray(_to_pil(img).filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)


def fractal_noise(h: int, w: int, rng: np.random.Generator, octaves: int = 4) -> np.ndarray:
    """Sum of up-sampled random grids -> smooth 0..1 noise field."""
    out = np.zeros((h, w), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = 2 ** (o + 2)
        grid = rng.random((cells, cells)).astype(np.float32)
        up = np.asarray(_to_pil(grid * 255).resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
        out += amp * up
        total += amp
        amp *= 0.5
    return out / total


def render_drops(
    tile: np.ndarray,
    rng: np.random.Generator,
    n_drops: int | None = None,
    min_r: int = 6,
    max_r: int = 22,
) -> tuple[np.ndarray, np.ndarray]:
    """Paint adherent water drops onto ``tile`` (H,W,3 uint8).

    Returns (image, mask) where mask is a boolean H,W array of drop pixels.
    """
    h, w, _ = tile.shape
    img = tile.astype(np.float32)
    mask = np.zeros((h, w), dtype=bool)
    if n_drops is None:
        n_drops = int(rng.integers(1, 4))

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    blurred_bg = _blur(img, 1.5)

    for _ in range(n_drops):
        r = float(rng.integers(min_r, max_r + 1))
        cy = float(rng.uniform(r * 0.5, h - r * 0.5))
        cx = float(rng.uniform(r * 0.5, w - r * 0.5))
        # slight ellipse (gravity elongates drops)
        ay = rng.uniform(1.0, 1.35)
        dy, dx = (yy - cy) / (r * ay), (xx - cx) / r
        d = np.sqrt(dy * dy + dx * dx)
        inside = d < 1.0

        # --- refraction: sample the scene minified and inverted about the drop centre
        k = rng.uniform(0.3, 0.6)  # minification
        sy = np.clip(cy - dy * r * ay * k * 2.0, 0, h - 1).astype(np.int32)
        sx = np.clip(cx - dx * r * k * 2.0, 0, w - 1).astype(np.int32)
        refracted = blurred_bg[sy, sx]

        # --- dark rim from total internal reflection near the edge
        rim = np.clip((d - 0.75) / 0.25, 0, 1) ** 2
        shade = 1.0 - 0.6 * rim

        # --- specular highlight (small bright spot offset toward upper-left)
        hy, hx = cy - 0.4 * r * ay, cx - 0.4 * r
        spec = np.exp(-(((yy - hy) ** 2) + ((xx - hx) ** 2)) / (2 * (0.18 * r) ** 2))
        drop_pix = refracted * shade[..., None] + 255.0 * spec[..., None] * 0.9

        alpha = np.clip((1.0 - d) / 0.12, 0, 1)[..., None]  # soft edge
        img = img * (1 - alpha) + drop_pix * alpha
        mask |= inside

    return np.clip(img, 0, 255).astype(np.uint8), mask


def render_frost(
    tile: np.ndarray,
    rng: np.random.Generator,
    severity: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Cover ``tile`` with ice / frost.  Returns (image, mask)."""
    h, w, _ = tile.shape
    img = tile.astype(np.float32)
    if severity is None:
        severity = float(rng.uniform(0.45, 0.95))

    # scatter: blur + desaturate + lift toward white
    blurred = _blur(img, 1.0 + 3.0 * severity)
    gray = blurred.mean(axis=2, keepdims=True)
    desat = blurred * (1 - 0.7 * severity) + gray * (0.7 * severity)
    lifted = desat * (1 - 0.55 * severity) + 255.0 * (0.55 * severity)

    # crystal texture: thresholded fractal noise gives feathery bright veins
    n = fractal_noise(h, w, rng, octaves=5)
    veins = np.clip((n - 0.45) * 6.0, 0, 1)
    edges = np.abs(n - 0.5) < 0.03
    tex = 0.35 * veins + 0.6 * edges.astype(np.float32)
    out = lifted + 255.0 * tex[..., None] * severity * 0.6

    # frost is usually patchy: mask where coverage noise is above a threshold
    cov = fractal_noise(h, w, rng, octaves=3)
    thresh = 1.0 - severity  # more severe -> more covered
    mask = cov > thresh * 0.8
    alpha = np.clip((cov - thresh * 0.8) / 0.15, 0, 1)[..., None]
    img = img * (1 - alpha) + out * alpha
    return np.clip(img, 0, 255).astype(np.uint8), mask


def procedural_background(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """A random 'scene' for when no real clean photos are available:
    a colour gradient plus a few blurred rectangles and lines."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    c0 = rng.uniform(40, 220, size=3)
    c1 = rng.uniform(40, 220, size=3)
    t = ((yy / h) * rng.uniform(-1, 1) + (xx / w) * rng.uniform(-1, 1) + 1) / 2
    img = c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]
    for _ in range(int(rng.integers(2, 6))):
        y0, x0 = rng.integers(0, h), rng.integers(0, w)
        y1, x1 = min(h, y0 + rng.integers(4, h // 2)), min(w, x0 + rng.integers(4, w // 2))
        img[y0:y1, x0:x1] = rng.uniform(0, 255, size=3)
    img = _blur(img, rng.uniform(0.0, 1.2))
    noise = rng.normal(0, 4, size=img.shape).astype(np.float32)
    return np.clip(img + noise, 0, 255).astype(np.uint8)
