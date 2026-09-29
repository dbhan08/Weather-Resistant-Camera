# Weather-Resistant Camera

An STM32-based enclosure that keeps a camera lens usable in rain and frost.
A vision model on the host PC (or, with the TFLite Micro path, on the MCU)
detects water on the lens and triggers a servo wiper; an on-die thermistor
turns a heating pad on below a threshold.  UIUC ECE 445 senior design,
Spring 2025.

## Run it

```bash
# firmware: open Final.ioc in STM32CubeIDE, build main.c, flash the Nucleo-F4
# vision (original OpenCV heuristic):
python final_code.py               # webcam -> HSV mask -> % coverage -> "START" over serial
# vision (CNN, see CNN/README.md):
python -m lens_soiling.infer runs/procedural/soilnet.pt --camera 1 --port COM3
```

## How it works

- **Firmware (`main.c`).**  TIM2 PWM drives the servo; `Set_Servo_Angle`
  maps 0–180° to a 210–1050 tick pulse.  ADC1 reads the internal temperature
  sensor with the factory `TS_CAL1/2` calibration, and drives a MOSFET on PA5
  to switch the heater.  USART2 at 115200 baud accepts 5-byte commands
  (`START`, `STOPP`) from the PC; `START` sweeps the wiper 60→115→60°.
- **Vision, heuristic (`final_code.py`).**  HSV threshold on low saturation
  and high value, morphological close, contours, enclosing circles, then
  percent of masked pixels.  Over 5 % sends `START`.
- **Vision, CNN (`CNN/`).**  Tile-level classifier: a ported pretrained
  raindrop CNN distilled into a ~20 k-parameter int8 model for TFLite Micro,
  plus a tested PyTorch fallback trained on synthetic drops and frost.
- **Hardware.**  KiCad PCB (`PCB Design*/`), 5 V and 3.3 V regulators, MOSFET
  heater switch, logic-level shifter, servo header.  Demo ran on the Nucleo
  dev board after the second PCB's MCU was damaged during hand soldering.

## Layout

```
main.c, Final.ioc          STM32 firmware and CubeMX project
final_code.py              OpenCV heuristic + serial trigger (PC)
python_to_stm_comm.py      serial protocol smoke test
CNN/                       CNN detection: pretrained port + from-scratch pipeline
Servo Motor code/, Temperature sensor code/   subsystem test firmware
PCB Design*/               KiCad
Lab Notebooks/             per-member design logs
```

## Stack

C (STM32 HAL), Python, OpenCV, PyTorch, TensorFlow Lite Micro, KiCad.
