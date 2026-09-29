"""Port the pretrained AlexNet-30^2 raindrop classifier to Keras.

Source: Guo, Akcay, Adey, Breckon, "On the impact of varying region proposal
strategies for raindrop detection and classification using CNNs", ICIP 2018.
Weights: https://github.com/tobybreckon/raindrop-detection-cnn
(`download-models.sh` -> models/alexnet_30_2_classification.tfl, MIT).

Why a port is needed
--------------------
The weights are a TFLearn checkpoint written by TensorFlow 1.x.  TFLearn
and TF1 do not run on current Python or Apple Silicon, and the TFLite
converter cannot read a `.tfl` file.  TF2 *can* still read TF1 checkpoint
variables through `tf.train.load_checkpoint`, so we rebuild the identical
graph in Keras and copy the tensors across by name.

Architecture (verbatim from raindrop_classification.py, 30x30x3 input):
    conv 96 11x11 s4 relu -> maxpool 3 s2 -> LRN
    conv 256 5x5 relu     -> maxpool 3 s2 -> LRN
    conv 384 3x3 relu -> conv 384 3x3 relu -> conv 256 3x3 relu
    maxpool 3 s2 -> LRN
    fc 4096 tanh -> dropout .5 -> fc 4096 tanh -> dropout .5 -> fc 2 softmax
TFLearn defaults that matter: padding 'same' everywhere, LRN
depth_radius=5, bias=1.0, alpha=1e-4, beta=0.75, input scaled to [0, 1].

Spatial trace: 30 -> 8 -> 4 -> 4 -> 2 -> 2 -> 1.  The flatten is 1x1x256,
so there is no NHWC/NCHW ordering problem in the first dense layer.

Usage
-----
    python -m pretrained.port_breckon models/alexnet_30_2_classification.tfl \
        --out runs/breckon --samples path/to/raindrop-detection-cnn/images/classification
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    import tensorflow as tf
    from tensorflow import keras
except ImportError as e:  # pragma: no cover - documented dependency
    raise SystemExit("pip install tensorflow  (this module needs TF >= 2.10)") from e

PATCH = 30
CLASSES = ("non_raindrop", "raindrop")  # TFLearn label order: 0 = no drop, 1 = drop

# TFLearn names layers by type with a running suffix.  Keras layer name -> checkpoint scope.
_NAME_MAP = {
    "conv1": "Conv2D",
    "conv2": "Conv2D_1",
    "conv3": "Conv2D_2",
    "conv4": "Conv2D_3",
    "conv5": "Conv2D_4",
    "fc1": "FullyConnected",
    "fc2": "FullyConnected_1",
    "fc3": "FullyConnected_2",
}


def lrn(x):
    return tf.nn.local_response_normalization(x, depth_radius=5, bias=1.0, alpha=1e-4, beta=0.75)


def build_alexnet30(num_classes: int = 2, dropout: float = 0.5) -> keras.Model:
    L = keras.layers
    inp = L.Input((PATCH, PATCH, 3), name="patch")
    x = L.Conv2D(96, 11, strides=4, padding="same", activation="relu", name="conv1")(inp)
    x = L.MaxPool2D(3, strides=2, padding="same")(x)
    x = L.Lambda(lrn, name="lrn1")(x)
    x = L.Conv2D(256, 5, padding="same", activation="relu", name="conv2")(x)
    x = L.MaxPool2D(3, strides=2, padding="same")(x)
    x = L.Lambda(lrn, name="lrn2")(x)
    x = L.Conv2D(384, 3, padding="same", activation="relu", name="conv3")(x)
    x = L.Conv2D(384, 3, padding="same", activation="relu", name="conv4")(x)
    x = L.Conv2D(256, 3, padding="same", activation="relu", name="conv5")(x)
    x = L.MaxPool2D(3, strides=2, padding="same")(x)
    x = L.Lambda(lrn, name="lrn3")(x)
    x = L.Flatten()(x)
    x = L.Dense(4096, activation="tanh", name="fc1")(x)
    x = L.Dropout(dropout)(x)
    x = L.Dense(4096, activation="tanh", name="fc2")(x)
    x = L.Dropout(dropout)(x)
    out = L.Dense(num_classes, activation="softmax", name="fc3")(x)
    return keras.Model(inp, out, name="alexnet30_2")


def list_checkpoint_vars(tfl_path: str) -> dict[str, list[int]]:
    reader = tf.train.load_checkpoint(tfl_path)
    return {k: list(v) for k, v in reader.get_variable_to_shape_map().items()}


def load_tfl_weights(model: keras.Model, tfl_path: str) -> dict:
    """Copy TF1 checkpoint tensors into the Keras model.  Returns a report of
    every variable matched, so a wrong mapping fails loudly, not silently."""
    reader = tf.train.load_checkpoint(tfl_path)
    shapes = reader.get_variable_to_shape_map()
    report = {"loaded": [], "skipped": sorted(k for k in shapes if "Momentum" in k or "Adam" in k)}
    for keras_name, scope in _NAME_MAP.items():
        layer = model.get_layer(keras_name)
        w_key, b_key = f"{scope}/W", f"{scope}/b"
        if w_key not in shapes:
            raise KeyError(f"{w_key} not in checkpoint; vars are: {sorted(shapes)[:20]} ...")
        w, b = reader.get_tensor(w_key), reader.get_tensor(b_key)
        kw, kb = layer.get_weights()
        if w.shape != kw.shape or b.shape != kb.shape:
            raise ValueError(f"{keras_name}: ckpt {w.shape}/{b.shape} vs keras {kw.shape}/{kb.shape}")
        layer.set_weights([w, b])
        report["loaded"].append({"layer": keras_name, "ckpt": scope, "shape": list(w.shape)})
    return report


def preprocess(bgr_or_rgb: np.ndarray, is_bgr: bool = False) -> np.ndarray:
    """Match the original script: resize to 30x30 (Lanczos), RGB, /255."""
    from PIL import Image

    img = bgr_or_rgb[..., ::-1] if is_bgr else bgr_or_rgb
    img = np.asarray(Image.fromarray(img).resize((PATCH, PATCH), Image.LANCZOS), dtype=np.float32)
    return img / 255.0


def check_on_samples(model: keras.Model, folder: Path) -> dict:
    """The repo ships 16 classification sample patches named by class.
    Report per-file prediction so the port can be verified by eye."""
    from PIL import Image

    out = {}
    for p in sorted(folder.glob("*")):
        if p.suffix.lower() not in {".jpg", ".png", ".jpeg"}:
            continue
        x = preprocess(np.asarray(Image.open(p).convert("RGB")))[None]
        prob = model.predict(x, verbose=0)[0]
        out[p.name] = {"raindrop_prob": float(prob[1]), "pred": CLASSES[int(prob.argmax())]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tfl", help="path prefix of the .tfl checkpoint (without .index/.data suffix)")
    ap.add_argument("--out", default="runs/breckon")
    ap.add_argument("--samples", default=None, help="folder of sample patches to sanity-check")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = build_alexnet30()
    report = {"checkpoint_vars": list_checkpoint_vars(a.tfl), "params": int(model.count_params())}
    report.update(load_tfl_weights(model, a.tfl))
    if a.samples:
        report["samples"] = check_on_samples(model, Path(a.samples))
    model.save(out / "alexnet30_2.keras")
    (out / "port_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "checkpoint_vars"}, indent=2))
    print(f"saved {out / 'alexnet30_2.keras'}  params={report['params']:,}")


if __name__ == "__main__":
    main()
