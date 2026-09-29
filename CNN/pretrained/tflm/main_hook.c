/* How the MCU loop in ../../../main.c changes when inference moves on-chip.
 *
 * Today main.c waits for a 5-byte "START" over UART from the PC and then
 * sweeps the servo 60->115->60 degrees in 3-degree steps.  With the student
 * on the MCU, the trigger comes from SoilCoverage() instead.  The heater
 * path is untouched: it is already driven by the on-die thermistor.
 *
 * Frame source: a DCMI camera (e.g. OV7670 / OV2640) DMA'd into RGB565 and
 * expanded to RGB888 per tile, or a QVGA RGB888 buffer if RAM allows
 * (320*240*3 = 230 KB -> needs an F7/H7, not the F4 Nucleo).  See README.
 */

#include <stdint.h>

extern int  SoilInit(void);
extern float SoilCoverage(const uint8_t* frame, int width, int height, uint8_t* grid_out);
extern void Set_Servo_Angle(void* htim, uint32_t channel, uint8_t angle);   /* from main.c */

#define WIPE_THRESHOLD   0.05f    /* same 5 % as the HSV heuristic */
#define WIPE_COOLDOWN_MS 4000u    /* one sweep takes ~4 s at 100 ms/step */

static uint32_t last_wipe_ms;

void Soil_Setup(void) {
  if (!SoilInit()) {
    /* fall back to PC-driven START/STOPP commands */
  }
}

/* Call from the main while(1) once per captured frame. */
void Soil_Tick(const uint8_t* rgb_frame, int w, int h, uint32_t now_ms, void* htim, uint32_t ch) {
  float cover = SoilCoverage(rgb_frame, w, h, 0);
  if (cover >= WIPE_THRESHOLD && (now_ms - last_wipe_ms) > WIPE_COOLDOWN_MS) {
    for (uint8_t a = 60; a <= 115; a += 3) { Set_Servo_Angle(htim, ch, a); /* HAL_Delay(100) */ }
    for (uint8_t a = 115; a > 60;  a -= 3) { Set_Servo_Angle(htim, ch, a); /* HAL_Delay(100) */ }
    last_wipe_ms = now_ms;
  }
}
