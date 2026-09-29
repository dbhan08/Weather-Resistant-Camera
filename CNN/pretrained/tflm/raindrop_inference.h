// On-MCU raindrop tile classifier (TensorFlow Lite Micro, int8 student).
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RAINDROP_TILE 48          // student input side, pixels
#define RAINDROP_CHANNELS 3       // RGB888

// Load the model from flash and allocate the tensor arena. Returns 1 on success.
int RaindropInit(void);

// Classify every RAINDROP_TILE x RAINDROP_TILE tile of an RGB888 frame.
// Returns the fraction of tiles classed "raindrop" in [0,1].
// grid_out (rows*cols bytes, may be NULL) receives 1 per raindrop tile.
float RaindropCoverage(const uint8_t* frame, int width, int height, uint8_t* grid_out);

// Microseconds spent in the last RaindropCoverage() call (for your own benchmarking).
uint32_t RaindropLastInferenceUs(void);

#ifdef __cplusplus
}
#endif
