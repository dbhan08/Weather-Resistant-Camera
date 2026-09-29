"""Build docs/Adaptive_Camera_Cleaning_System.pdf with reportlab."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = Path(__file__).parent / "Adaptive_Camera_Cleaning_System.pdf"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=16, spaceBefore=14, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=ss["Normal"], fontSize=10, leading=13.5, alignment=TA_LEFT, spaceAfter=5)
CODE = ParagraphStyle("Code", parent=ss["Code"], fontSize=8.2, leading=10.5, backColor=colors.whitesmoke,
                      borderPadding=4, spaceBefore=3, spaceAfter=7, leftIndent=4)
SMALL = ParagraphStyle("Small", parent=P, fontSize=8.5, leading=11, textColor=colors.grey)


def p(t):
    return Paragraph(t, P)


def bullets(items):
    return ListFlowable([ListItem(Paragraph(i, P), leftIndent=12) for i in items], bulletType="bullet",
                        start="•", leftIndent=14, bulletFontSize=8)


def numbered(items):
    return ListFlowable([ListItem(Paragraph(i, P), leftIndent=14) for i in items], bulletType="1", leftIndent=16)


def code(t):
    return Paragraph(t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"), CODE)


def table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def cell(t):
    return Paragraph(t, ParagraphStyle("cell", parent=P, fontSize=9, leading=11.5, spaceAfter=0))


story = []
story += [Paragraph("Adaptive Camera Cleaning System", ss["Title"]),
          Paragraph("How it works, what I built, and how the vision model is integrated with the camera and the "
                    "microcontroller. UIUC ECE 445 senior design, Spring 2025. Team of three. "
                    "Repo: github.com/dbhan08/Weather-Resistant-Camera", SMALL),
          Spacer(1, 8)]

# ---------------------------------------------------------------- 1
story += [Paragraph("1. What the system does", H1),
          p("A weather-resistant enclosure keeps a camera lens usable in rain and frost. An STM32F4 microcontroller "
            "watches the lens with a small camera, decides when the lens is wet, and runs a servo-driven wiper. "
            "It also reads its on-die temperature sensor and switches a heating pad through a MOSFET when the "
            "temperature drops below a threshold. Both actions are automatic. No human input is needed once it is powered."),
          p("The project was split into seven subsystems: heater, temperature sensor, microcontroller, wiper, power, "
            "computer, and camera. The camera and computer subsystems are the vision path, which is the part I owned.")]

story += [Paragraph("2. What I was responsible for", H1),
          bullets([
              "<b>Camera subsystem.</b> Researched and selected the camera module (DFRobot FIT0701 for the bench demo), "
              "got a live feed working with OpenCV, and later wrote the DCMI capture path for the on-chip design.",
              "<b>Vision algorithm.</b> Wrote the raindrop detector: first the OpenCV HSV and contour heuristic used at the "
              "demo, then the CNN pipeline (pretrained port, fine-tune, distillation, int8 export) and the TensorFlow "
              "Lite Micro inference code that runs on the STM32.",
              "<b>Camera-to-MCU integration.</b> Defined the 5-byte serial protocol (START / STOPP) between the PC and the "
              "STM32, wrote the Python side, and then replaced it with an on-MCU loop so the PC is not in the loop.",
              "<b>Documentation.</b> Wrote the Introduction, Problem Statement and Proposed Solution in the proposal and "
              "design document, and the Requirements and Verification section of the final paper, including all "
              "verification data.",
              "<b>Shared hardware work.</b> PCB layout iterations in KiCad with the team, machine-shop enclosure "
              "meetings, soldering and bring-up of the first PCB.",
          ])]

# ---------------------------------------------------------------- 3
story += [Paragraph("3. Hardware and firmware overview", H1),
          table([
              ["Block", "Part / peripheral", "What it does"],
              [cell("MCU"), cell("STM32F4 (Nucleo dev board for the demo; custom PCB designed)"),
               cell("Runs the control loop, PWM, ADC, UART, DCMI")],
              [cell("Wiper"), cell("Hobby servo on TIM2 CH1 PWM"),
               cell("Sweeps 60 to 115 degrees and back in 3-degree steps, 100 ms per step")],
              [cell("Heater"), cell("Heating pad through a MOSFET on PA5, logic-level shifter, indicator LED"),
               cell("On when temperature is below threshold")],
              [cell("Sensor"), cell("STM32 internal temperature sensor on ADC1"),
               cell("Factory-calibrated at 30 C and 110 C, minus a 9 C offset found in testing")],
              [cell("Camera"), cell("OV7670 on DCMI + DMA (on-chip path); USB camera + PC (demo path)"),
               cell("160x120 RGB565 frames")],
              [cell("Power"), cell("5 V and 3.3 V regulators"), cell("Servo and heater on 5 V, MCU on 3.3 V")],
              [cell("Link"), cell("USART2, 115200 baud"), cell("Status log; START / STOPP commands in the demo path")],
          ], [0.8 * inch, 2.9 * inch, 3.0 * inch]),
          Spacer(1, 6),
          p("The servo angle is converted to a PWM compare value with a linear map from 0 to 180 degrees onto "
            "210 to 1050 timer ticks:"),
          code("void Set_Servo_Angle(TIM_HandleTypeDef *htim, uint32_t ch, uint8_t angle) {\n"
               "    uint32_t pulse = 210 + (angle * (1050 - 210) / 180);\n"
               "    __HAL_TIM_SET_COMPARE(htim, ch, pulse);\n}"),
          p("The heater trigger uses only the thermistor. Vision never drives the heater. Ice looks like many "
            "things on a lens; temperature does not. The wiper is also locked out when the temperature is at or "
            "below 0 C so the servo never fights ice.")]

# ---------------------------------------------------------------- 4
story += [Paragraph("4. Vision, version 1: the OpenCV heuristic used at the demo", H1),
          p("The first plan was a CNN on the PC. It lagged the live feed, so for the demo I wrote a classical "
            "OpenCV pipeline in <i>final_code.py</i>. Every 4 seconds:"),
          numbered([
              "Grab a frame and flip it vertically, because the camera is mounted upside down in the enclosure.",
              "Convert to HSV. Keep pixels with saturation below 40 (water on glass looks grey) AND value above 100 "
              "(rejects shadows).",
              "Morphological close with a 15x15 ellipse to fill each drop into a solid blob.",
              "Find external contours and sort by area. Skip the largest (the lens ring). Enclose the next two in "
              "minimum circles and fill them black, so a drop's bright interior counts as covered, not just its edge.",
              "Compute the percentage of black pixels. Over 5 % sends the 5-byte string START to the STM32 over serial.",
          ]),
          code("_, s_mask = cv2.threshold(s, 40, 255, cv2.THRESH_BINARY_INV)\n"
               "_, v_mask = cv2.threshold(v, 100, 255, cv2.THRESH_BINARY)\n"
               "closed = cv2.morphologyEx(cv2.bitwise_and(s_mask, v_mask), cv2.MORPH_CLOSE, kernel)\n"
               "...\n"
               "if black_percent > 5:\n"
               "    ser.write(b\"START\")   # STM32 sweeps the wiper"),
          p("On the STM32, the main loop blocks up to 1 s on a 5-byte UART receive. START runs the sweep. STOPP is a "
            "no-op kept for protocol symmetry."),
          Paragraph("What went wrong", H2),
          p("The heuristic false-fired on glare and surface texture. With the TA we found the root cause: the lens sits "
            "millimetres from the surface where drops form, so the camera is effectively zoomed in and small artifacts "
            "look like drops. I reworked the detector to key on the dark drop edges, then enclose and fill them to "
            "estimate true coverage, and ran 100 trials on varied test images to check it. That version is what ran "
            "at the final demo.")]

# ---------------------------------------------------------------- 5
story += [PageBreak(), Paragraph("5. Vision, version 2: a CNN on the microcontroller", H1),
          p("The CNN path removes the PC from the loop. The MCU captures the frame, classifies it, and triggers the "
            "wiper itself. The design is a <b>tile classifier</b>: the frame is cut into a fixed grid of tiles, each "
            "tile is labelled raindrop or clean, and the fraction of raindrop tiles is the coverage number. This is the "
            "coverage-metric idea from automotive lens-soiling work (Valeo SoilingNet / TiledSoilingNet) and it maps "
            "directly onto the 5 % rule from the heuristic."),
          Paragraph("5.1 Where the model comes from", H2),
          p("No public model exists for water on a lens, so I started from the closest published one: the AlexNet-30<super>2</super> "
            "raindrop classifier from Guo, Akcay, Adey and Breckon (ICIP 2018), which reports 0.95 accuracy on "
            "30x30 patches from a windshield camera. Its weights are a TensorFlow 1 / TFLearn checkpoint, which no "
            "current toolchain can run or convert. TF2 can still read TF1 checkpoint variables, so <i>port_breckon.py</i> "
            "rebuilds the exact graph in Keras and copies every tensor by name, asserting shapes:"),
          code("_NAME_MAP = {\"conv1\": \"Conv2D\", \"conv2\": \"Conv2D_1\", ..., \"fc3\": \"FullyConnected_2\"}\n"
               "reader = tf.train.load_checkpoint(tfl_path)\n"
               "w, b = reader.get_tensor(f\"{scope}/W\"), reader.get_tensor(f\"{scope}/b\")\n"
               "layer.set_weights([w, b])"),
          Paragraph("5.2 Fine-tuning to our lens", H2),
          p("Breckon's camera looked through a windshield. Ours is millimetres from the drops, so drops are larger and "
            "blurrier. <i>data_windshield.py</i> cuts labelled 30x30 patches from the RaindropsOnWindshield dataset "
            "(8,190 frames with pixel masks, CC BY 4.0). A patch is positive if the mask covers at least 30 % of it, "
            "and negative only if the patch and a one-patch margin are mask-free, so borderline drops never leak "
            "into negatives. Splits are by video sequence so no clip appears on both sides. <i>finetune.py</i> then "
            "does the standard two stages: dense head only at lr 1e-3, then all layers at 1e-5 with early stopping, "
            "with flips and 45-degree rotations as in the paper."),
          Paragraph("5.3 Why it had to be distilled", H2),
          p("After three pooling layers a 30x30 input collapses to 1x1x256, followed by 256x4096 and 4096x4096 dense "
            "layers. That is about 18 million parameters: 75 MB in fp32, 19 MB even in int8. The STM32F4 has 512 KB "
            "of flash and 192 KB of SRAM. The model also uses local response normalization, which TensorFlow Lite "
            "Micro does not implement. So the fine-tuned network is the <b>teacher</b> on the PC and a small "
            "<b>student</b> runs on the chip."),
          p("The student (<i>distill_student.py</i>) takes a 48x48 tile, uses a stem convolution and five "
            "depthwise-separable blocks, global average pooling and two logits. About 20 k parameters, ReLU only, "
            "and just the ops TFLM has: CONV_2D, DEPTHWISE_CONV_2D, MEAN, FULLY_CONNECTED. It is trained with "
            "knowledge distillation (Hinton et al. 2015): the loss mixes KL divergence to the teacher's softened "
            "probabilities at temperature 4 with cross-entropy on the hard label. The soft labels carry the "
            "teacher's uncertainty on glare and texture, which is exactly the failure mode of the heuristic."),
          code("loss = alpha * KL(teacher_soft_T, student_soft_T) * T**2 + (1 - alpha) * CE(y, student_logits)\n"
               "# T = 4, alpha = 0.7"),
          Paragraph("5.4 Quantization and export", H2),
          p("<i>to_tflite.py</i> converts the student to full-integer int8: int8 weights, int8 activations, int8 input "
            "and output. The converter needs a representative dataset, a few hundred real tiles it pushes through the "
            "fp32 graph to record each tensor's range. I use validation patches, not training patches, so the ranges "
            "are not tuned on the images the weights were fitted to. The script then emits the model as a C array "
            "(<i>raindrop_student_int8.cc</i>) and a report with the byte size, op list, input scale and zero point, "
            "and int8-versus-fp32 argmax agreement.")]

# ---------------------------------------------------------------- 6
story += [Paragraph("6. Integration with the camera and the STM32", H1),
          p("Three firmware files under <i>CNN/pretrained/tflm/</i> replace the PC. Memory budget: 38 KB RGB565 DMA "
            "frame, 58 KB RGB888 frame, 48 KB TFLM tensor arena, about 25 KB of model in flash."),
          Paragraph("6.1 Camera capture: camera_dcmi.c", H2),
          p("The OV7670 is configured over SCCB (I2C, address 0x42) for QQVGA 160x120 RGB565: reset, QVGA RGB mode, "
            "RGB565 output, enable the down-scaler and set the divider to /4 in both axes, auto gain / white balance / "
            "exposure on. Its pixel clock, HREF and VSYNC lines go to the DCMI peripheral, which DMA's one frame into "
            "SRAM in snapshot mode. The capture call blocks on the frame-complete callback with a 500 ms timeout, "
            "then converts RGB565 to RGB888 by replicating the high bits into the low bits so full white maps to "
            "255, not 248."),
          code("HAL_DCMI_Start_DMA(&hdcmi, DCMI_MODE_SNAPSHOT, (uint32_t)s_frame565, (CAM_W*CAM_H*2)/4);\n"
               "while (!s_frame_done) { if (HAL_GetTick() - t0 > 500) return 0; }\n"
               "rgb888[3*i+0] = (r5 << 3) | (r5 >> 2);   // and likewise g6, b5"),
          Paragraph("6.2 Inference: raindrop_inference.cc", H2),
          p("At boot, <i>RaindropInit</i> loads the model from the flash array, registers only the six ops the student "
            "uses in a MicroMutableOpResolver, allocates tensors in the 48 KB arena, and checks the input is int8 "
            "48x48x3 with a 2-way output. Per frame, <i>RaindropCoverage</i> walks the 3x2 grid of 48 px tiles. Each "
            "tile is copied out of the frame row by row and quantized with the scale and zero point the converter "
            "stored in the model. The student was trained on pixel/255, so the mapping is:"),
          code("q = round((pixel / 255) / input_scale) + input_zero_point, clamped to [-128, 127]"),
          p("After <i>Invoke</i>, the tile is raindrop if the second int8 logit is larger than the first. Argmax on "
            "quantized logits is order-preserving, so no dequantization is needed. The function returns raindrop "
            "tiles divided by total tiles and, optionally, the per-tile grid. The Cortex-M DWT cycle counter times the "
            "whole pass; <i>RaindropLastInferenceUs</i> exposes it for logging."),
          Paragraph("6.3 The control loop: main_raindrop.c", H2),
          p("This is the original <i>main.c</i> with the UART trigger replaced by the CNN. Once per second:"),
          numbered([
              "Read the on-die temperature through ADC1 with the factory TS_CAL1 / TS_CAL2 constants. Below the "
              "threshold, pull PA5 low to switch the heater MOSFET on.",
              "Capture a 160x120 frame over DCMI.",
              "Run <i>RaindropCoverage</i> on the frame.",
              "If coverage is at least 5 %, temperature is above 0 C, and 4 s have passed since the last wipe, "
              "sweep the servo 60 to 115 degrees and back.",
              "Print one status line on USART2: temperature, heater state, coverage, the 6-character tile grid, "
              "inference microseconds, and whether a wipe ran.",
          ]),
          code("if (cam_ok && nn_ok && CameraCaptureRGB888(s_frame))\n"
               "    cover = RaindropCoverage(s_frame, CAM_W, CAM_H, s_grid);\n"
               "if (cover >= WIPE_THRESHOLD && temp_c > 0.0f && (HAL_GetTick() - last_wipe) > WIPE_COOLDOWN_MS) {\n"
               "    Wipe(); last_wipe = HAL_GetTick();\n}"),
          p("The status line is the measurement channel. Logging USART2 during a rain test gives per-frame latency "
            "(nn_us) and lets each printed grid be checked against what is visible on the lens, which is how "
            "accuracy is scored."),
          Paragraph("6.4 Build", H2),
          p("In STM32CubeIDE: enable DCMI, a DMA2 stream, I2C1 and a 12 to 24 MHz clock output for the camera XCLK in "
            "the .ioc; import a tflite-micro tree generated with <i>create_tflm_tree.py</i>; compile it as C++17 with "
            "TF_LITE_STATIC_MEMORY and CMSIS_NN; add the three firmware files and the generated model array; exclude "
            "the old main.c. Link with nano.specs and -u _printf_float so the status line prints floats.")]

# ---------------------------------------------------------------- 7
story += [Paragraph("7. Test and verification", H1),
          bullets([
              "<b>Subsystem tests.</b> Servo tested on a servo tester at the machine shop (found a dead motor). Power "
              "rails verified at 5 V and 3.3 V. MOSFET output verified with and without a control signal. Temperature "
              "readings compared against a reference, giving the 9 C offset.",
              "<b>Heuristic.</b> 100 trials on varied test images.",
              "<b>CNN pipeline on the PC.</b> The from-scratch fallback in <i>lens_soiling/</i> has nine pytest unit and "
              "integration tests (train, export, infer). The pretrained pipeline writes a JSON report at every stage: "
              "port (per-variable match and sample-patch predictions), fine-tune (test accuracy), distillation "
              "(student test accuracy), TFLite (int8 vs fp32 agreement, byte size, op list).",
              "<b>End-to-end.</b> Final demo with all subsystems interacting: freezing simulated with a cooler of ice and "
              "a 20.5 C threshold, wiper triggered by detected obstruction, LED confirming heater state. Outdoor test "
              "of the enclosure.",
          ])]

# ---------------------------------------------------------------- 8
story += [Paragraph("8. Problems and how they were handled", H1),
          table([
              ["Problem", "Cause", "Fix"],
              [cell("CNN on the PC lagged the live feed"), cell("Per-frame inference in Python on a laptop, no batching"),
               cell("Shipped the OpenCV heuristic for the demo; later moved a distilled int8 CNN onto the MCU")],
              [cell("Heuristic false positives on glare and texture"),
               cell("Lens millimetres from the drop surface, so texture is magnified"),
               cell("Edge-based detection with circle fill; then the tile CNN trained on real drops")],
              [cell("Pretrained model cannot run on STM32"), cell("18 M params, LRN op not in TFLM"),
               cell("Knowledge distillation into a 20 k-param student with only TFLM ops")],
              [cell("Second PCB MCU destroyed"), cell("Fine-pitch package, hand soldering"),
               cell("Final demo on the Nucleo dev board with the same firmware")],
              [cell("Servo not moving"), cell("Dead motor, not wiring or code"), cell("Confirmed on a servo tester, replaced")],
              [cell("No freezing conditions available"), cell("Bench test indoors"),
               cell("Cooler of ice with the heater threshold raised to 20.5 C")],
          ], [2.0 * inch, 2.2 * inch, 2.5 * inch])]

# ---------------------------------------------------------------- 9
story += [Paragraph("9. Interview talking points", H1),
          bullets([
              "<b>Tradeoff.</b> Tile classification with a coverage number instead of segmentation: far cheaper on an "
              "MCU, and it maps straight onto the wipe rule. You lose drop shape, which you do not need.",
              "<b>Tradeoff.</b> Distillation instead of training the small net from scratch: the teacher's soft labels "
              "transfer what it knows about glare, and you get to use published weights instead of collecting a "
              "large dataset.",
              "<b>Design choice.</b> Heater on the thermistor, wiper on vision, and a 0 C lockout so the two never "
              "conflict.",
              "<b>Broke.</b> The near-lens geometry that made the heuristic false-fire; found with the TA by looking "
              "at the mechanical setup, not the code.",
              "<b>Next time.</b> Mount the camera farther from the wet surface. Add a frost class. Use an STM32H7 with "
              "more SRAM so a full QVGA frame and a wider student fit.",
          ])]

story += [Spacer(1, 10),
          Paragraph("References: Guo, Akcay, Adey, Breckon, ICIP 2018 (github.com/tobybreckon/raindrop-detection-cnn). "
                    "Soboleva & Shipitko, RaindropsOnWindshield, 2021 (Zenodo 4680442). Uricar et al., SoilingNet, "
                    "ITSC 2019. Hinton, Vinyals, Dean, Distilling the Knowledge in a Neural Network, 2015. "
                    "Howard et al., MobileNets, 2017.", SMALL)]

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                        topMargin=0.8 * inch, bottomMargin=0.8 * inch, title="Adaptive Camera Cleaning System",
                        author="Deyvik Bhan")
doc.build(story)
print(OUT)
