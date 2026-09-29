// TensorFlow Lite Micro inference for the distilled raindrop student.
//
// RaindropInit() once at boot, RaindropCoverage() once per captured frame.
// The model is the int8 .tflite emitted by pretrained/to_tflite.py, linked
// in as the C array g_raindrop_student[] (raindrop_student_int8.cc).
//
// Memory budget, width-1.0 student:
//   flash  g_raindrop_student_len bytes  (~25 KB) + tflite-micro core
//   sram   kArenaBytes tensor arena      (48 KB, see note in tflm/README.md)
//
// Ops used by the student (and nothing else, so the resolver stays small):
//   CONV_2D, DEPTHWISE_CONV_2D, MEAN, FULLY_CONNECTED, RESHAPE, SOFTMAX

#include "raindrop_inference.h"

#include <cstring>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "raindrop_student_int8.h"  // g_raindrop_student, g_raindrop_student_len
#include "stm32f4xx_hal.h"          // HAL_GetTick / DWT cycle counter for timing

namespace {

constexpr int kArenaBytes = 48 * 1024;
alignas(16) uint8_t g_arena[kArenaBytes];

const tflite::Model* g_model = nullptr;
tflite::MicroInterpreter* g_interp = nullptr;
TfLiteTensor* g_in = nullptr;
TfLiteTensor* g_out = nullptr;
tflite::MicroMutableOpResolver<6> g_resolver;
uint32_t g_last_us = 0;

// Cortex-M DWT cycle counter -> microseconds, for RaindropLastInferenceUs().
inline void CycleCounterStart() {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}
inline uint32_t CycleCounterUs() { return DWT->CYCCNT / (SystemCoreClock / 1000000U); }

// Quantize one RGB888 tile into the int8 input tensor.  The student was
// trained on pixel/255, and the converter baked (scale, zero_point) for that
// real-valued input into the model, so: q = round(pixel/255 / scale) + zp.
void FillInput(const uint8_t* rgb) {
  const float inv = 1.0f / (255.0f * g_in->params.scale);
  const int zp = g_in->params.zero_point;
  int8_t* dst = g_in->data.int8;
  const int n = RAINDROP_TILE * RAINDROP_TILE * RAINDROP_CHANNELS;
  for (int i = 0; i < n; ++i) {
    int q = static_cast<int>(rgb[i] * inv + 0.5f) + zp;
    dst[i] = static_cast<int8_t>(q < -128 ? -128 : (q > 127 ? 127 : q));
  }
}

// 1 if the tile is "raindrop" (class index 1).  Argmax on the int8 output
// is order-preserving, so no dequantization is needed.
int ClassifyTile(const uint8_t* rgb) {
  FillInput(rgb);
  if (g_interp->Invoke() != kTfLiteOk) return 0;
  const int8_t* o = g_out->data.int8;
  return o[1] > o[0];
}

}  // namespace

extern "C" int RaindropInit(void) {
  tflite::InitializeTarget();
  g_model = tflite::GetModel(g_raindrop_student);
  if (g_model->version() != TFLITE_SCHEMA_VERSION) return 0;

  g_resolver.AddConv2D();
  g_resolver.AddDepthwiseConv2D();
  g_resolver.AddMean();
  g_resolver.AddFullyConnected();
  g_resolver.AddReshape();
  g_resolver.AddSoftmax();

  static tflite::MicroInterpreter interp(g_model, g_resolver, g_arena, kArenaBytes);
  g_interp = &interp;
  if (g_interp->AllocateTensors() != kTfLiteOk) return 0;
  g_in = g_interp->input(0);
  g_out = g_interp->output(0);
  return g_in->type == kTfLiteInt8 && g_in->dims->data[1] == RAINDROP_TILE &&
         g_in->dims->data[3] == RAINDROP_CHANNELS && g_out->dims->data[1] == 2;
}

extern "C" float RaindropCoverage(const uint8_t* frame, int width, int height, uint8_t* grid_out) {
  static uint8_t tile[RAINDROP_TILE * RAINDROP_TILE * RAINDROP_CHANNELS];
  const int rows = height / RAINDROP_TILE, cols = width / RAINDROP_TILE;
  if (rows == 0 || cols == 0) return 0.0f;

  CycleCounterStart();
  int hits = 0;
  for (int r = 0; r < rows; ++r) {
    for (int c = 0; c < cols; ++c) {
      // Copy the tile out of the frame row by row (frame is row-major RGB888).
      for (int y = 0; y < RAINDROP_TILE; ++y) {
        const uint8_t* src = frame + ((r * RAINDROP_TILE + y) * width + c * RAINDROP_TILE) * RAINDROP_CHANNELS;
        std::memcpy(tile + y * RAINDROP_TILE * RAINDROP_CHANNELS, src, RAINDROP_TILE * RAINDROP_CHANNELS);
      }
      const int k = ClassifyTile(tile);
      hits += k;
      if (grid_out) grid_out[r * cols + c] = static_cast<uint8_t>(k);
    }
  }
  g_last_us = CycleCounterUs();
  return static_cast<float>(hits) / static_cast<float>(rows * cols);
}

extern "C" uint32_t RaindropLastInferenceUs(void) { return g_last_us; }
