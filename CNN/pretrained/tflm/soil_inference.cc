// TensorFlow Lite Micro inference for the distilled soiling student.
//
// Drop-in for an STM32 project that already has tflite-micro in the tree.
// Call SoilInit() once, then SoilCoverage() on every camera frame.  The
// return value is the fraction of 48x48 tiles the network calls "raindrop";
// main.c compares it with the same 5 % threshold the old HSV path used and
// runs the servo sweep.
//
// Memory (width 1.0 student, measured on the PC converter, confirm on target):
//   flash: g_soil_student_len bytes (~25 KB)   sram: kArenaBytes (~40 KB)
//
// NOT built or run in this repo.  Written against tflite-micro's
// MicroInterpreter API as of 2024; check names against your vendored copy.

#include <cstdint>
#include <cstring>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "soil_student_int8.h"  // g_soil_student, g_soil_student_len (from to_tflite.py)

namespace {

constexpr int kTile = 48;
constexpr int kChannels = 3;
constexpr int kArenaBytes = 48 * 1024;
alignas(16) uint8_t g_arena[kArenaBytes];

const tflite::Model* g_model = nullptr;
tflite::MicroInterpreter* g_interp = nullptr;
TfLiteTensor* g_in = nullptr;
TfLiteTensor* g_out = nullptr;

// Only the ops the student uses: keeps the resolver, and flash, small.
tflite::MicroMutableOpResolver<6> g_resolver;

}  // namespace

bool SoilInit() {
  g_model = tflite::GetModel(g_soil_student);
  if (g_model->version() != TFLITE_SCHEMA_VERSION) return false;

  g_resolver.AddConv2D();
  g_resolver.AddDepthwiseConv2D();
  g_resolver.AddMean();             // GlobalAveragePooling2D lowers to MEAN
  g_resolver.AddFullyConnected();
  g_resolver.AddReshape();
  g_resolver.AddSoftmax();          // present only if the exporter added it; harmless otherwise

  static tflite::MicroInterpreter interp(g_model, g_resolver, g_arena, kArenaBytes);
  g_interp = &interp;
  if (g_interp->AllocateTensors() != kTfLiteOk) return false;
  g_in = g_interp->input(0);
  g_out = g_interp->output(0);
  return g_in->type == kTfLiteInt8 && g_in->dims->data[1] == kTile;
}

// Quantize one RGB888 tile (row-major, kTile*kTile*3 bytes) into the input
// tensor using the scale / zero-point baked into the .tflite by the
// converter.  The model was trained on x/255, so real = pixel/255.
static void FillInput(const uint8_t* rgb) {
  const float scale = g_in->params.scale;
  const int zp = g_in->params.zero_point;
  const float inv = 1.0f / (255.0f * scale);
  int8_t* dst = g_in->data.int8;
  const int n = kTile * kTile * kChannels;
  for (int i = 0; i < n; ++i) {
    int q = static_cast<int>(rgb[i] * inv + 0.5f) + zp;
    if (q < -128) q = -128;
    if (q > 127) q = 127;
    dst[i] = static_cast<int8_t>(q);
  }
}

// Returns 1 if the tile is classed "raindrop" (index 1), else 0.
static int ClassifyTile(const uint8_t* rgb) {
  FillInput(rgb);
  if (g_interp->Invoke() != kTfLiteOk) return 0;
  const int8_t* o = g_out->data.int8;
  return o[1] > o[0] ? 1 : 0;  // argmax on quantized logits is order-preserving
}

// frame: RGB888, width*height*3, row-major.  Edge remainders are ignored,
// matching the fixed-grid choice in lens_soiling/dataset.py.
float SoilCoverage(const uint8_t* frame, int width, int height, uint8_t* grid_out /* rows*cols, may be null */) {
  static uint8_t tile[kTile * kTile * kChannels];
  const int rows = height / kTile, cols = width / kTile;
  int hits = 0;
  for (int r = 0; r < rows; ++r) {
    for (int c = 0; c < cols; ++c) {
      for (int y = 0; y < kTile; ++y) {
        const uint8_t* src = frame + ((r * kTile + y) * width + c * kTile) * kChannels;
        std::memcpy(tile + y * kTile * kChannels, src, kTile * kChannels);
      }
      const int k = ClassifyTile(tile);
      hits += k;
      if (grid_out) grid_out[r * cols + c] = static_cast<uint8_t>(k);
    }
  }
  return rows * cols ? static_cast<float>(hits) / static_cast<float>(rows * cols) : 0.0f;
}
