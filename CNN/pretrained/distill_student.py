"""Distill the (fine-tuned) AlexNet-30^2 teacher into an MCU-sized student.

Why distil instead of shipping the teacher
------------------------------------------
After three 'same'-padded pools a 30x30 input is 1x1x256, then fc1 is
256x4096 and fc2 is 4096x4096.  That is ~18 M parameters: ~75 MB in fp32
and ~19 MB even in int8.  The STM32F4 dev board has 512 KB flash and 192 KB
SRAM.  Also, TensorFlow Lite Micro has no LRN kernel.  So the teacher runs
on the PC, and a student with only TFLM-supported ops runs on the MCU.

Student: 48x48 input (tiles from the frame, downscaled), depthwise-
separable MobileNet-style blocks, ~20 k params, ReLU only, global average
pool, 2 logits.  Same family as ../lens_soiling/model.py, written in Keras
here so the TFLite converter is the native export path.

Loss (Hinton et al. 2015): alpha * KL(teacher_soft || student_soft, T) * T^2
                          + (1 - alpha) * CE(hard_label, student)
Teacher soft labels are computed once per epoch on the fly from the same
augmented batch, so the student also learns the teacher's uncertainty on
glare / texture patches -- exactly the false-positive cases the HSV
heuristic got wrong.

    python -m pretrained.distill_student runs/breckon_ft/alexnet30_2_ft.keras data/patches --out runs/student
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

from .port_breckon import PATCH as TEACHER_PATCH, CLASSES, lrn  # noqa: F401

STUDENT_SIDE = 48


def _cbr(x, c, k, s, groups_dw=False, name=None):
    L = keras.layers
    if groups_dw:
        x = L.DepthwiseConv2D(k, strides=s, padding="same", use_bias=False, name=f"{name}_dw")(x)
    else:
        x = L.Conv2D(c, k, strides=s, padding="same", use_bias=False, name=name)(x)
    x = L.BatchNormalization(name=f"{name}_bn")(x)
    return L.ReLU(name=f"{name}_relu")(x)


def ds_block(x, cout, stride, name):
    x = _cbr(x, None, 3, stride, groups_dw=True, name=name)
    return _cbr(x, cout, 1, 1, name=f"{name}_pw")


def build_student(width: float = 1.0, num_classes: int = len(CLASSES)) -> keras.Model:
    c = lambda n: max(8, int(round(n * width)))  # noqa: E731
    L = keras.layers
    inp = L.Input((STUDENT_SIDE, STUDENT_SIDE, 3), name="tile")
    x = _cbr(inp, c(16), 3, 2, name="stem")           # 48 -> 24
    x = ds_block(x, c(32), 2, "b1")                   # 24 -> 12
    x = ds_block(x, c(32), 1, "b2")
    x = ds_block(x, c(64), 2, "b3")                   # 12 -> 6
    x = ds_block(x, c(64), 1, "b4")
    x = ds_block(x, c(128), 2, "b5")                  # 6 -> 3
    x = L.GlobalAveragePooling2D()(x)
    x = L.Dropout(0.1)(x)
    out = L.Dense(num_classes, name="logits")(x)     # logits; softmax applied in loss / on MCU
    return keras.Model(inp, out, name=f"raindrop_student_w{width}")


class Distiller(keras.Model):
    def __init__(self, student: keras.Model, teacher: keras.Model, T: float = 4.0, alpha: float = 0.7):
        super().__init__()
        self.student, self.teacher, self.T, self.alpha = student, teacher, T, alpha
        self.teacher.trainable = False
        self.kl = keras.losses.KLDivergence()
        self.ce = keras.losses.CategoricalCrossentropy(from_logits=True)
        self.acc = keras.metrics.CategoricalAccuracy(name="accuracy")

    def call(self, x, training=False):
        return self.student(x, training=training)

    def _teacher_probs(self, x):
        xt = tf.image.resize(x, (TEACHER_PATCH, TEACHER_PATCH), method="lanczos3")
        return self.teacher(xt, training=False)  # softmax output

    def train_step(self, data):
        x, y = data
        p_t = self._teacher_probs(x)
        # re-temper teacher softmax: p^(1/T) renormalised == softmax(logits/T)
        p_t_T = tf.math.pow(p_t + 1e-8, 1.0 / self.T)
        p_t_T = p_t_T / tf.reduce_sum(p_t_T, axis=1, keepdims=True)
        with tf.GradientTape() as tape:
            logits = self.student(x, training=True)
            p_s_T = tf.nn.softmax(logits / self.T)
            loss = self.alpha * self.kl(p_t_T, p_s_T) * self.T**2 + (1 - self.alpha) * self.ce(y, logits)
        grads = tape.gradient(loss, self.student.trainable_variables)
        self.optimizer.apply_gradients(zip(grads, self.student.trainable_variables))
        self.acc.update_state(y, logits)
        return {"loss": loss, "accuracy": self.acc.result()}

    def test_step(self, data):
        x, y = data
        logits = self.student(x, training=False)
        self.acc.update_state(y, logits)
        return {"loss": self.ce(y, logits), "accuracy": self.acc.result()}

    @property
    def metrics(self):
        return [self.acc]


def make_ds(folder: Path, batch: int, shuffle: bool) -> tf.data.Dataset:
    ds = keras.utils.image_dataset_from_directory(
        folder, label_mode="categorical", class_names=list(CLASSES),
        image_size=(STUDENT_SIDE, STUDENT_SIDE), interpolation="lanczos3", batch_size=batch, shuffle=shuffle, seed=0,
    )
    aug = keras.Sequential([keras.layers.RandomFlip(), keras.layers.RandomBrightness(0.15), keras.layers.RandomContrast(0.15)])
    def prep(x, y):
        x = x / 255.0
        return (aug(x, training=True) if shuffle else x), y
    return ds.map(prep, num_parallel_calls=tf.data.AUTOTUNE).prefetch(tf.data.AUTOTUNE)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("teacher")
    ap.add_argument("patches")
    ap.add_argument("--out", default="runs/student")
    ap.add_argument("--width", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--T", type=float, default=4.0)
    ap.add_argument("--alpha", type=float, default=0.7)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(a.patches)
    tr, va, te = (make_ds(root / s, a.batch, s == "train") for s in ("train", "val", "test"))

    teacher = keras.models.load_model(a.teacher, custom_objects={"lrn": lrn}, safe_mode=False)
    student = build_student(a.width)
    d = Distiller(student, teacher, a.T, a.alpha)
    d.compile(optimizer=keras.optimizers.AdamW(3e-3, weight_decay=1e-4))
    cb = [keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=5, restore_best_weights=True)]
    h = d.fit(tr, validation_data=va, epochs=a.epochs, callbacks=cb, verbose=2)

    test = d.evaluate(te, verbose=0, return_dict=True)
    student.save(out / "student.keras")
    report = {"student_params": int(student.count_params()), "teacher_params": int(teacher.count_params()),
              "history": h.history, "test": test}
    (out / "distill_report.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
