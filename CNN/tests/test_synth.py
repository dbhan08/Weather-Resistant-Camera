import numpy as np
from lens_soiling.synth import render_drops, render_frost, procedural_background, fractal_noise


def test_background_shape_dtype():
    bg = procedural_background(64, 64, np.random.default_rng(0))
    assert bg.shape == (64, 64, 3) and bg.dtype == np.uint8


def test_drops_mask_and_change():
    rng = np.random.default_rng(1)
    bg = procedural_background(64, 64, rng)
    img, mask = render_drops(bg, rng, n_drops=2)
    assert img.shape == bg.shape and mask.shape == (64, 64)
    assert 0.02 < mask.mean() < 0.9
    # pixels changed mostly inside the mask
    diff = np.abs(img.astype(int) - bg.astype(int)).sum(-1) > 10
    assert diff[mask].mean() > diff[~mask].mean()


def test_frost_brightens_and_desaturates():
    rng = np.random.default_rng(2)
    bg = procedural_background(64, 64, rng)
    img, mask = render_frost(bg, rng, severity=0.9)
    assert mask.mean() > 0.3
    assert img[mask].mean() > bg[mask].mean()  # frost lifts toward white
    sat = lambda a: (a.max(-1) - a.min(-1)).mean()  # noqa: E731
    assert sat(img[mask].astype(int)) < sat(bg[mask].astype(int))


def test_fractal_noise_range():
    n = fractal_noise(32, 48, np.random.default_rng(3))
    assert n.shape == (32, 48) and 0 <= n.min() and n.max() <= 1
