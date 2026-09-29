"""Fine-tune the ported AlexNet-30^2 on our own patches.

Why: Breckon's data is a forward camera behind a windshield.  Our lens
sits millimetres from the drops (lab notebook, 2025-04-05), so drops are
larger, blurrier and lower-contrast.  A short fine-tune on
RaindropsOnWindshield patches plus frames from the FIT0701 camera adapts
the classifier to that domain without training from scratch.

Two stages, the usual transfer-learning recipe:
  1. freeze conv1..conv5, train fc1..fc3 at lr 1e-3 for --head-epochs
  2. unfreeze everything, lr 1e-5, --full-epochs, early stop on val loss

    python -m pretrained.finetune runs/breckon/alexnet30_2.keras data/patches --out runs/breckon_ft
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import tensorflow as tf
    from tensorflow import keras
except ImportError as e:  # pragma: no cover
    raise SystemExit("pip install tensorflow") from e

from .port_breckon import PATCH, CLASSES, lrn  # noqa: F401  (lrn needed to deserialize the Lambda)


def make_ds(folder: Path, batch: int, shuffle: bool) -> tf.data.Dataset:
    ds = keras.utils.image_dataset_from_directory(
        folder, labels="inferred", label_mode="categorical", class_names=list(CLASSES),
        image_size=(PATCH, PATCH), interpolation="lanczos3", batch_size=batch, shuffle=shuffle, seed=0,
    )
    aug = keras.Sequential([
        keras.layers.RandomFlip("horizontal_and_vertical"),
        keras.layers.RandomRotation(0.125),  # +-45 deg, as in the paper
        keras.layers.RandomBrightness(0.15),
        keras.layers.RandomContrast(0.15),
    ])
    def prep(x, y):
        x = x / 255.0
        return (aug(x, training=True) if shuffle else x), y
    return ds.map(prep, num_parallel_calls=tf.data.AUTOTUNE).prefetch(tf.data.AUTOTUNE)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("patches", help="folder with train/ val/ test/ from data_windshield.py")
    ap.add_argument("--out", default="runs/breckon_ft")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--head-epochs", type=int, default=5)
    ap.add_argument("--full-epochs", type=int, default=10)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(a.patches)
    tr, va, te = (make_ds(root / s, a.batch, s == "train") for s in ("train", "val", "test"))

    model = keras.models.load_model(a.model, custom_objects={"lrn": lrn}, safe_mode=False)
    base = {"test_before": model.evaluate(te, verbose=0, return_dict=True)} if model.compiled_metrics else {}

    # stage 1: head only
    for layer in model.layers:
        layer.trainable = layer.name.startswith("fc")
    model.compile(keras.optimizers.Adam(1e-3), "categorical_crossentropy", metrics=["accuracy"])
    h1 = model.fit(tr, validation_data=va, epochs=a.head_epochs, verbose=2)

    # stage 2: everything, tiny lr
    for layer in model.layers:
        layer.trainable = True
    model.compile(keras.optimizers.Adam(1e-5), "categorical_crossentropy", metrics=["accuracy"])
    cb = [keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True),
          keras.callbacks.ModelCheckpoint(str(out / "alexnet30_2_ft.keras"), save_best_only=True)]
    h2 = model.fit(tr, validation_data=va, epochs=a.full_epochs, callbacks=cb, verbose=2)

    test = model.evaluate(te, verbose=0, return_dict=True)
    report = {**base, "head_history": h1.history, "full_history": h2.history, "test_after": test}
    (out / "finetune_report.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps(test, indent=2))


if __name__ == "__main__":
    main()
