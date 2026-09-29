// OV7670 camera over STM32 DCMI + DMA, QQVGA (160x120) RGB565.
//
// Frame budget: 160*120*2 = 38,400 bytes for the raw frame plus an
// RGB888 conversion buffer of 160*120*3 = 57,600 bytes.  Both fit the
// STM32F4's 192 KB SRAM next to the 48 KB TFLM arena.  A 160x120 frame
// gives a 3 x 2 grid of 48 px tiles (edge remainders dropped).
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CAM_W 160
#define CAM_H 120

// Configure OV7670 registers over SCCB (I2C), start DCMI in snapshot mode.
// Returns 1 on success.
int CameraInit(void);

// Capture one frame, blocking until the DMA transfer completes (about 33 ms
// at 30 fps).  Fills rgb888 (CAM_W*CAM_H*3 bytes).  Returns 1 on success.
int CameraCaptureRGB888(uint8_t* rgb888);

#ifdef __cplusplus
}
#endif
