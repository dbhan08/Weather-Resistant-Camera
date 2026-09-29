"""LensSoilNet: a MobileNet-style tile classifier small enough for a
Cortex-M7 / M4 running TensorFlow Lite Micro or STM32Cube.AI.

Design notes
------------
* Input 3x64x64, output 3 logits (clean / water / ice).
* Stem 3x3 stride-2 conv, then depthwise-separable blocks (Howard et al.,
  MobileNetV1) which cut MACs ~8x versus dense 3x3 convs.
* No residuals or squeeze-excite: every op maps to a TFLM / Cube.AI
  builtin (CONV_2D, DEPTHWISE_CONV_2D, RELU, MEAN, FULLY_CONNECTED).
* Conv -> BN -> ReLU triplets fold into one fused int8 conv at export, so
  activations are quantized *after* the ReLU and no int8 range is wasted
  on negative values.  Post-training observers bound the range, so ReLU6
  is not needed.
* BatchNorm folds into the preceding conv at export time.
* Width multiplier lets you trade accuracy for flash/RAM on the MCU.
"""
from __future__ import annotations

import torch
from torch import nn

from . import CLASSES


def _cbr(cin: int, cout: int, k: int, s: int, groups: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, k, s, padding=k // 2, groups=groups, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class DSBlock(nn.Module):
    """Depthwise 3x3 -> pointwise 1x1."""

    def __init__(self, cin: int, cout: int, stride: int):
        super().__init__()
        self.dw = _cbr(cin, cin, 3, stride, groups=cin)
        self.pw = _cbr(cin, cout, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.pw(self.dw(x))


class LensSoilNet(nn.Module):
    def __init__(self, width: float = 1.0, num_classes: int = len(CLASSES), dropout: float = 0.1):
        super().__init__()
        c = lambda n: max(8, int(round(n * width)))  # noqa: E731
        self.features = nn.Sequential(
            _cbr(3, c(16), 3, 2),        # 64 -> 32
            DSBlock(c(16), c(32), 2),    # 32 -> 16
            DSBlock(c(32), c(32), 1),
            DSBlock(c(32), c(64), 2),    # 16 -> 8
            DSBlock(c(64), c(64), 1),
            DSBlock(c(64), c(128), 2),   # 8 -> 4
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(c(128), num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x).flatten(1)
        return self.fc(self.drop(x))


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def count_macs(m: nn.Module, tile: int = 64) -> int:
    """Multiply-accumulates for one tile, via forward hooks on conv/linear."""
    macs = 0

    def hook(mod, inp, out):
        nonlocal macs
        if isinstance(mod, nn.Conv2d):
            k = mod.kernel_size[0] * mod.kernel_size[1] * (mod.in_channels // mod.groups)
            macs += k * out.numel()
        elif isinstance(mod, nn.Linear):
            macs += mod.in_features * mod.out_features

    hs = [mod.register_forward_hook(hook) for mod in m.modules() if isinstance(mod, (nn.Conv2d, nn.Linear))]
    m.eval()
    with torch.no_grad():
        m(torch.zeros(1, 3, tile, tile))
    for h in hs:
        h.remove()
    return macs
