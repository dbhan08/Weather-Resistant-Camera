# Rain detection CNN for the camera lens

The vision subsystem is a tile-level raindrop classifier that runs on the
STM32 under TensorFlow Lite Micro.  The MCU captures a 160x120 frame over
DCMI, classifies each 48 px tile with an int8 CNN, and triggers the wiper
when the fraction of raindrop tiles passes 5 %.  It replaces the PC-side HSV
threshold + contour heuristic in `../final_code.py`, which false-fired on
glare and surface texture (lab notebook, 2025-03-07 and 2025-04-05).

| Path | Folder | What it is |
|---|---|---|
| **Deployed** | `pretrained/` + `pretrained/tflm/` | Breckon's AlexNet-30² raindrop weights (ICIP 2018) → Keras port → fine-tune → distilled 20 k-param student → full-int8 TFLite → C array → TFLite Micro firmware |
| Fallback / experiments | `lens_soiling/` | PyTorch net trained on synthetic drops and frost; `pytest tests` passes |

## Pretrained path: how it works

1. **Port the weights (`port_breckon.py`).**  The published model is a
   TFLearn checkpoint from TensorFlow 1.x.  TF1 and TFLearn do not install on
   current Python or Apple Silicon, and the TFLite converter cannot read a
   `.tfl`.  But TF2's `tf.train.load_checkpoint` still reads TF1 variables,
   so the script rebuilds the exact graph in Keras and copies each tensor
   by name (`Conv2D`, `Conv2D_1`, ... `FullyConnected_2`).  Every shape is
   asserted, and the repo's 16 sample patches are re-classified so the port
   can be checked before anything else runs.
   Architecture: five convs (96·11×11/4, 256·5×5, 384·3×3, 384·3×3,
   256·3×3) with 3×3/2 max-pools and local response normalization, then
   4096-tanh, 4096-tanh, 2-softmax.  Input is a 30×30 RGB patch scaled to
   [0, 1].  The paper reports 0.95 accuracy on windshield-camera patches.
2. **Get labelled patches (`data_windshield.py`).**  RaindropsOnWindshield
   (8,190 frames, 3,390 with drops, pixel masks, CC BY 4.0) is cut into
   30×30 patches: positive if the mask covers ≥ 30 % of the patch, negative
   only if the patch *and a one-patch margin* are mask-free.  Splits are by
   video sequence so frames from one clip never leak across train / test.
3. **Fine-tune (`finetune.py`).**  Breckon's camera looked through a
   windshield.  Ours sits millimetres from the drops, so drops are bigger and
   blurrier.  Standard two-stage transfer: head only at lr 1e-3, then all
   layers at 1e-5 with early stopping.  Flips and ±45° rotation, as in the
   paper.
4. **Distill to an MCU-sized student (`distill_student.py`).**  After three
   pools a 30×30 input is 1×1×256, then 256×4096 and 4096×4096 dense layers:
   about 18 M parameters, 75 MB fp32, 19 MB int8.  The STM32F4 Nucleo has
   512 KB flash and 192 KB SRAM, and TFLite Micro has no LRN kernel.  So the
   teacher stays on the PC and a 48×48 depthwise-separable student
   (~20 k params, only CONV_2D / DEPTHWISE_CONV_2D / MEAN / FULLY_CONNECTED)
   is trained on the teacher's softened probabilities (Hinton et al. 2015,
   T = 4, α = 0.7) plus the hard labels.
5. **Quantize and emit C (`to_tflite.py`).**  Full-integer int8 with a
   representative dataset of validation patches, int8 in/out, then a
   `g_raindrop_student[]` C array.  The report records op list, byte size, input
   scale/zero-point, and int8-vs-fp32 argmax agreement.
6. **Run on the board (`tflm/`).**  `raindrop_inference.cc` sets up
   `MicroInterpreter` with a six-op resolver and a 48 KB arena, quantizes
   each tile with the converter's scale/zero-point, and returns the fraction
   of tiles classed raindrop.  `main_hook.c` shows the change to `main.c`:
   the servo sweep triggers on coverage ≥ 5 % with a 4 s cooldown instead
   of on a UART `START`.

```bash
# in a venv with tensorflow>=2.10, pillow, numpy
bash raindrop-detection-cnn/download-models.sh            # Breckon weights (MIT)
python -m pretrained.port_breckon models/alexnet_30_2_classification.tfl --out runs/breckon --samples raindrop-detection-cnn/images/classification
zenodo_get https://zenodo.org/record/4680442 --output-dir data/RaindropsOnWindshield
python -m pretrained.data_windshield data/RaindropsOnWindshield --out data/patches
python -m pretrained.finetune runs/breckon/alexnet30_2.keras data/patches --out runs/breckon_ft
python -m pretrained.distill_student runs/breckon_ft/alexnet30_2_ft.keras data/patches --out runs/student
python -m pretrained.to_tflite runs/student/student.keras data/patches/val --out runs/tflite --name raindrop_student
```

### Why not ship the pretrained model as-is

- It is 18 M parameters.  Too big for any STM32 by two orders of magnitude.
- It uses LRN, which TFLite Micro does not implement.
- It was trained on a windshield view, not a lens millimetres from the water.
- It has no ice class.  Ice is left to the thermistor, which the firmware
  already does.  A frost class can be added to the student later from the
  synthetic frost renderer in `lens_soiling/synth.py` or from real frames.

## From-scratch path (tested)

`lens_soiling/` is a PyTorch pipeline that renders adherent drops (minified,
inverted, blurred scene with a dark rim and specular highlight) and frost
(blur, desaturation, lift to white, fractal crystal texture) onto clean
tiles, trains a 19.7 k-parameter net, quantizes it to int8 and dumps a C
weight header.  On procedural backgrounds it reaches 98.5 % validation
accuracy with 100 % int8/fp32 argmax agreement.  That number is synthetic
and must not be quoted as real-world accuracy.

```bash
pip install -r requirements.txt
python -m pytest tests -q
python -m lens_soiling.train --epochs 8 --out runs/procedural
python -m lens_soiling.export runs/procedural/soilnet.pt --out runs/procedural
python -m lens_soiling.infer runs/procedural/soilnet.pt --image test.jpg
```

## Firmware

`pretrained/tflm/` holds the on-MCU side: `raindrop_inference.cc` (TFLM
interpreter, 6-op resolver, 48 KB arena, per-tile int8 quantization, DWT
cycle timing), `camera_dcmi.c` (OV7670 QQVGA RGB565 over DCMI + DMA),
and `main_raindrop.c`, the full main loop: thermistor → heater MOSFET,
capture → CNN → coverage → servo sweep, one status line per second over
USART2 with coverage, tile grid and inference microseconds.  Build steps
and the SRAM budget are in `pretrained/tflm/README.md`.

## Numbers

Record them from the USART2 status line (`nn_us`, `cover`, `grid`) and
from `export_report.json` / `tflite_report.json`.  Fill this table from
your own logs; do not copy synthetic numbers here.

| Metric | Value | Source |
|---|---|---|
| Student params / int8 model bytes | | `tflite_report.json` |
| int8 vs fp32 argmax agreement | | `tflite_report.json` |
| Test accuracy on held-out lens patches | | `distill_report.json` |
| On-MCU latency per 3x2 tile frame | | `nn_us` in the USART2 log |
| Tensor arena used | | `arena_used_bytes()` |

## References

- Guo, Akcay, Adey, Breckon. *On the impact of varying region proposal strategies for raindrop detection and classification using CNNs.* ICIP 2018. Code + weights: https://github.com/tobybreckon/raindrop-detection-cnn
- Soboleva, Shipitko. *Raindrops on Windshield: Dataset and Lightweight Gradient-Based Detection Algorithm.* 2021. https://github.com/EvoCargo/RaindropsOnWindshield
- Uřičář et al. *SoilingNet*, ITSC 2019; Das et al. *TiledSoilingNet*, 2020 (tile-level coverage idea).
- Qian et al. *Attentive GAN for Raindrop Removal*, CVPR 2018; You et al. *Adherent Raindrop Modeling*, TPAMI 2016 (drop appearance model).
- Hinton, Vinyals, Dean. *Distilling the Knowledge in a Neural Network.* 2015.
- Howard et al. *MobileNets.* 2017.

## Stack

Python, TensorFlow / Keras, TensorFlow Lite Micro, PyTorch, NumPy, Pillow, pytest, C/C++ on STM32 HAL.
