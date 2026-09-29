"""Run the tile classifier on a frame and drive the STM32 wiper / heater.

Frame-level decision (TiledSoilingNet-style coverage metric):
  water_cover = fraction of tiles predicted "water"
  ice_cover   = fraction of tiles predicted "ice"
  if water_cover >= --wipe-threshold  -> send START (servo wipe)
  if ice_cover   >= --heat-threshold  -> send HEATT (the firmware already
                                          heats from its own thermistor; this
                                          is a hint the lens looks frozen)

Examples
  python -m lens_soiling.infer runs/soilnet/soilnet.pt --image photo.jpg
  python -m lens_soiling.infer runs/soilnet/soilnet.pt --camera 1 --port COM3
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict

import numpy as np
import torch
from PIL import Image

from . import CLASSES, TILE
from .dataset import tile_frame
from .model import LensSoilNet


@dataclass
class FrameResult:
    rows: int
    cols: int
    water_cover: float
    ice_cover: float
    clean_cover: float
    grid: list  # rows x cols of class indices


@torch.no_grad()
def classify_frame(model: torch.nn.Module, frame: np.ndarray, tile: int = TILE) -> FrameResult:
    batch, (rows, cols) = tile_frame(frame, tile)
    pred = model(batch).argmax(1).numpy()
    counts = np.bincount(pred, minlength=len(CLASSES)) / pred.size
    return FrameResult(rows, cols, float(counts[1]), float(counts[2]), float(counts[0]), pred.reshape(rows, cols).tolist())


class Stm32Link:
    """5-byte command protocol used by main.c: START / STOPP (+ HEATT hint)."""

    def __init__(self, port: str | None, baud: int = 115200):
        self.ser = None
        if port:
            import serial  # pyserial, optional

            self.ser = serial.Serial(port, baudrate=baud, timeout=1)

    def send(self, cmd: bytes) -> str:
        assert len(cmd) == 5, "firmware reads exactly 5 bytes"
        if self.ser is None:
            return f"(dry-run) {cmd.decode()}"
        self.ser.write(cmd)
        return self.ser.readline().decode(errors="replace").strip()

    def close(self):
        if self.ser:
            self.ser.close()


def load_model(weights: str, width: float = 1.0) -> LensSoilNet:
    m = LensSoilNet(width=width)
    m.load_state_dict(torch.load(weights, map_location="cpu"))
    return m.eval()


def decide(res: FrameResult, link: Stm32Link, wipe_thr: float, heat_thr: float) -> list[str]:
    acts = []
    if res.water_cover >= wipe_thr:
        acts.append("START:" + link.send(b"START"))
    if res.ice_cover >= heat_thr:
        acts.append("HEATT:" + link.send(b"HEATT"))
    return acts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("weights")
    ap.add_argument("--width", type=float, default=1.0)
    ap.add_argument("--image", help="classify one image and exit")
    ap.add_argument("--camera", type=int, help="OpenCV camera index for a live loop")
    ap.add_argument("--port", default=None, help="serial port, e.g. COM3 or /dev/tty.usbmodem*")
    ap.add_argument("--wipe-threshold", type=float, default=0.05)
    ap.add_argument("--heat-threshold", type=float, default=0.15)
    ap.add_argument("--period", type=float, default=4.0, help="seconds between frames (wipe takes ~4 s)")
    a = ap.parse_args()

    model = load_model(a.weights, a.width)
    link = Stm32Link(a.port)
    try:
        if a.image:
            frame = np.asarray(Image.open(a.image).convert("RGB"))
            res = classify_frame(model, frame)
            print(json.dumps({**asdict(res), "actions": decide(res, link, a.wipe_threshold, a.heat_threshold)}, indent=1))
            return
        import cv2  # only needed for the live loop

        cap = cv2.VideoCapture(a.camera if a.camera is not None else 0)
        if not cap.isOpened():
            raise SystemExit("cannot open camera")
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            frame = cv2.flip(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), 0)
            res = classify_frame(model, frame)
            acts = decide(res, link, a.wipe_threshold, a.heat_threshold)
            print(f"water={res.water_cover:.2%} ice={res.ice_cover:.2%} {acts}")
            # overlay grid
            for r in range(res.rows):
                for c in range(res.cols):
                    k = res.grid[r][c]
                    if k:
                        col = (255, 0, 0) if k == 1 else (0, 200, 255)
                        cv2.rectangle(bgr, (c * TILE, (res.rows - 1 - r) * TILE), ((c + 1) * TILE, (res.rows - r) * TILE), col, 2)
            cv2.imshow("LensSoilNet", bgr)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            time.sleep(a.period)
        cap.release()
        cv2.destroyAllWindows()
    finally:
        link.close()


if __name__ == "__main__":
    main()
