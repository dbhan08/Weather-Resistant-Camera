"""Integration: tiny train -> export -> infer, all on procedural data."""
import json
from pathlib import Path

import numpy as np
import torch

from lens_soiling.train import train
from lens_soiling.export import export
from lens_soiling.infer import classify_frame, load_model, decide, Stm32Link
from lens_soiling.synth import procedural_background, render_drops


def test_train_export_infer(tmp_path: Path):
    s = train(None, tmp_path, epochs=3, n_train=768, n_val=192, batch=32, device="cpu", width=0.5)
    assert (tmp_path / "soilnet.pt").exists()
    assert s["val_accuracy"] > 0.5, s  # clearly above 1/3 chance after 3 tiny epochs

    rep = export(tmp_path / "soilnet.pt", tmp_path, width=0.5, n_calib=64)
    assert (tmp_path / "soilnet_int8_weights.h").exists()
    assert rep["int8_weight_bytes"] < rep["fp32_param_bytes"] / 3.5
    assert rep["int8_vs_fp32_argmax_agreement"] > 0.8

    model = load_model(str(tmp_path / "soilnet.pt"), width=0.5)
    rng = np.random.default_rng(0)
    frame = procedural_background(128, 192, rng)
    res = classify_frame(model, frame)
    assert (res.rows, res.cols) == (2, 3)
    assert abs(res.water_cover + res.ice_cover + res.clean_cover - 1) < 1e-6

    link = Stm32Link(None)  # dry-run
    acts = decide(res, link, wipe_thr=0.0, heat_thr=2.0)
    assert acts == ["START:(dry-run) START"]
    json.loads((tmp_path / "summary.json").read_text())
