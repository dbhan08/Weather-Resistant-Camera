"""Build docs/Adaptive_Camera_Cleaning_System.pdf with reportlab (plain-language re-learning guide)."""
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
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
P = ParagraphStyle("P", parent=ss["Normal"], fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6)
CODE = ParagraphStyle("Code", parent=ss["Code"], fontSize=8.0, leading=10.2, backColor=colors.whitesmoke,
                      borderPadding=4, spaceBefore=3, spaceAfter=8, leftIndent=4)
SMALL = ParagraphStyle("Small", parent=P, fontSize=8.5, leading=11, textColor=colors.grey)
BOX = ParagraphStyle("Box", parent=P, backColor=colors.HexColor("#fff8e1"), borderPadding=6, spaceBefore=4,
                     spaceAfter=10, leftIndent=2)


def p(t):
    return Paragraph(t, P)


def box(t):
    return Paragraph(t, BOX)


def bullets(items):
    return ListFlowable([ListItem(Paragraph(i, P), leftIndent=12) for i in items], bulletType="bullet",
                        start="•", leftIndent=14, bulletFontSize=8)


def numbered(items):
    return ListFlowable([ListItem(Paragraph(i, P), leftIndent=14) for i in items], bulletType="1", leftIndent=16)


def code(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")
    return Paragraph(t.replace("\n", "<br/>"), CODE)


def cell(t):
    return Paragraph(t, ParagraphStyle("cell", parent=P, fontSize=9, leading=11.5, spaceAfter=0))


def table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


story = [Paragraph("Adaptive Camera Cleaning System", ss["Title"]),
         Paragraph("A plain-language walkthrough of what it is, what I built, and how every part works, written "
                   "to re-learn the project from scratch. UIUC ECE 445 senior design, Jan to May 2025, team of "
                   "three. Repo: github.com/dbhan08/Weather-Resistant-Camera", SMALL),
         Spacer(1, 8)]

# ================================================================== 1
story += [Paragraph("1. The one-paragraph version", H1),
          p("Cameras outdoors get rain and frost on the lens and go blind. We built a box that fixes that by itself. "
            "Inside is a tiny computer chip (an STM32 microcontroller) with three jobs. It looks at the lens with a "
            "small camera and runs a neural network to decide if there is water on it. If there is, it moves a "
            "wiper across the lens with a servo motor. Separately, it reads a temperature sensor and turns on a "
            "heating pad when it gets cold, to melt frost. No laptop, no person. Plug it in and it looks after "
            "itself."),
          box("<b>The one thing to remember:</b> the whole product is a loop that runs once a second on the chip: "
              "read temperature, grab a picture, ask the neural network 'is the lens wet?', and move the wiper or "
              "switch the heater based on the answers."),
          table([["Result", "Value"],
                 [cell("Detection accuracy on our 100-image test set"), cell("89 %")],
                 [cell("When the wiper fires"), cell("5 % or more of the picture is classed as water")],
                 [cell("When the heater fires"), cell("temperature below the threshold (20.5 C in the demo)")],
                 [cell("Outdoor test"), cell("2 hours continuous")],
                 [cell("Size of the neural network on the chip"), cell("about 20,000 numbers, stored as 8-bit integers")]],
                [3.6 * inch, 3.1 * inch])]

# ================================================================== 2
story += [Paragraph("2. What I personally did", H1),
          p("Three people. The project was split into seven pieces: heater, temperature sensor, microcontroller, "
            "wiper, power, camera, and vision (the software that decides if the lens is wet). I owned the last two "
            "and the glue between them and the chip."),
          bullets([
              "<b>Camera.</b> Picked the camera modules, got a live picture out of them, and wrote the code that pulls "
              "a frame into the chip's memory.",
              "<b>Vision.</b> Wrote the rain detector. First a quick hand-tuned version for bring-up, then the real one: "
              "a neural network that I built from a published model, adapted to our lens, shrank to fit the chip, "
              "and got running on the chip.",
              "<b>Integration.</b> Wrote the main loop that ties temperature, camera, neural network, wiper and heater "
              "together, plus the serial-cable protocol we used during development and the logging used to score "
              "the test set.",
              "<b>Writing.</b> Introduction, Problem Statement and Proposed Solution in the proposal and design doc. "
              "The Requirements and Verification section of the final paper, with all the test data.",
              "<b>Shared.</b> Circuit board layout, machine-shop visits for the enclosure, soldering.",
          ])]

# ================================================================== 3
story += [Paragraph("3. The parts, and what each one physically does", H1),
          Paragraph("3.1 The microcontroller (STM32F4)", H2),
          p("A microcontroller is a whole small computer on one chip: processor, memory, and a set of built-in helper "
            "circuits called peripherals. Ours is an STM32F4 made by ST. It has 512 KB of flash (permanent storage "
            "where the program and the neural network live) and 192 KB of SRAM (working memory that is wiped at "
            "power-off). Those two numbers drove almost every design decision: the neural network and one camera "
            "frame both had to fit in 192 KB, together."),
          p("The peripherals we use, each explained where it comes up: a timer for the servo, an ADC for the "
            "temperature sensor, a UART for the serial cable, an I2C bus and a DCMI port for the camera, and a "
            "DMA engine to move camera data without the processor."),
          p("We designed our own circuit board for it in KiCad. The final demo ran the same program on a Nucleo, "
            "which is ST's ready-made board with the same chip, because we destroyed the chip on our second board "
            "while hand-soldering it. The chip's pins are 0.5 mm apart, and a hot iron on that pitch is unforgiving."),

          Paragraph("3.2 The wiper: a servo on a PWM timer", H2),
          p("A servo is a small motor that goes to an angle you ask for and holds it. You tell it the angle with a "
            "pulse: send a short electrical pulse every 20 milliseconds, and the width of the pulse is the angle. "
            "About 1 ms means one end, about 2 ms means the other end. This kind of signal is called PWM, pulse "
            "width modulation."),
          p("The chip's timer peripheral (TIM2) makes that signal for us. We set it up once so that one full 20 ms "
            "period equals some number of timer ticks, and then we just write a 'compare' value that says how many "
            "ticks the pulse should stay high. Bigger compare value, wider pulse, bigger angle. The two ends of our "
            "servo came out at 210 ticks and 1050 ticks, so the code maps 0 to 180 degrees onto that range with "
            "one line of arithmetic:"),
          code("void Set_Servo_Angle(TIM_HandleTypeDef *htim, uint32_t ch, uint8_t angle) {\n"
               "    uint32_t pulse = 210 + (angle * (1050 - 210) / 180);   // degrees -> ticks\n"
               "    __HAL_TIM_SET_COMPARE(htim, ch, pulse);                 // timer does the rest\n}"),
          p("A wipe is a sweep from 60 degrees to 115 and back, moving 3 degrees every 100 ms. Small steps with a "
            "pause make the arm move smoothly instead of slamming into the housing. The whole sweep takes about 3.7 s."),
          code("for (uint8_t a = 60; a <= 115; a += 3) { Set_Servo_Angle(&htim2, TIM_CHANNEL_1, a); HAL_Delay(100); }\n"
               "for (uint8_t a = 115; a > 60;  a -= 3) { Set_Servo_Angle(&htim2, TIM_CHANNEL_1, a); HAL_Delay(100); }"),

          Paragraph("3.3 The temperature sensor: an ADC reading", H2),
          p("The STM32 has a temperature sensor built into the silicon. It outputs a voltage that rises with "
            "temperature. To read a voltage in software you need an ADC, an analog-to-digital converter, which turns "
            "a voltage into a number. Ours is 12-bit, so it gives a number from 0 to 4095."),
          p("To turn that number into degrees you need two known points. ST measures every chip at the factory at "
            "30 C and 110 C and burns the two ADC readings into a fixed spot in memory. So the conversion is a "
            "straight line through those two points. We also found our readings ran 9 C high against a real "
            "thermometer, so we subtract 9."),
          code("#define TS_CAL1 (*((uint16_t*)0x1FFF7A2C))   // factory reading at 30 C\n"
               "#define TS_CAL2 (*((uint16_t*)0x1FFF7A2E))   // factory reading at 110 C\n"
               "HAL_ADC_Start(&hadc1);\n"
               "HAL_ADC_PollForConversion(&hadc1, HAL_MAX_DELAY);   // wait for the number\n"
               "raw = HAL_ADC_GetValue(&hadc1);\n"
               "t = (raw - TS_CAL1) * (110.0f - 30.0f) / (TS_CAL2 - TS_CAL1) + 30.0f - 9.0f;"),

          Paragraph("3.4 The heater: a MOSFET switch on one pin", H2),
          p("The heating pad needs more current than a chip pin can supply, and it runs at 5 V while the chip runs at "
            "3.3 V. So the chip does not power the heater. It flips a switch. The switch is a MOSFET, a transistor "
            "that lets current flow between two of its legs when a voltage is put on the third leg (the gate). "
            "Between the chip and the gate sits a level shifter, a small part that turns the chip's 3.3 V signal "
            "into the 5 V the gate wants."),
          p("Our wiring is inverted: the pad is on when pin PA5 is low. Pulling the pin low removes the voltage that "
            "was keeping the MOSFET off. An LED next to it lights when the heater is on so you can see the state."),
          code("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, temp_c < HEATER_THRESH_C ? GPIO_PIN_RESET : GPIO_PIN_SET);"),
          p("The threshold is 20.5 C in the demo code, not 0 C. We tested indoors with a cooler of ice, which cools "
            "the sensor to the high teens but never to freezing, so we raised the threshold to show the behaviour. "
            "In the field you set it to 1 or 2 C."),
          box("<b>Design rule:</b> the heater only ever listens to the temperature sensor. The camera and neural "
              "network never touch it. Lots of things look like frost in a picture. Temperature is unambiguous."),

          Paragraph("3.5 Power", H2),
          p("One 5 V regulator feeds the servo and the heater. A 3.3 V regulator feeds the chip. A regulator is a "
            "part that takes a messy input voltage and gives a steady fixed output. We verified both rails with a "
            "meter before soldering anything else, so a power fault could not be confused for a code bug later."),

          Paragraph("3.6 The serial cable (UART) for development and logging", H2),
          p("A UART sends bytes one at a time down two wires. The chip's USART2 runs at 115200 bits per second and "
            "shows up as a serial port on a laptop. During development the laptop sent the word START to run the "
            "wiper. In the final product the cable is optional: the chip prints one status line per second on it, "
            "and that log is how we scored the test set."),
          ]

# ================================================================== 4
story += [PageBreak(), Paragraph("4. The camera: getting a picture into the chip", H1),
          p("The camera is an OV7670, a fingernail-sized sensor that costs a few dollars. It does not send JPEG files. "
            "It streams raw pixels, one after another, on eight data wires, with a clock wire that ticks once per "
            "pixel and two more wires that say 'new row' and 'new frame'. Reading that with the processor would eat "
            "all its time, so the STM32 has a peripheral for it, DCMI (digital camera interface). DCMI grabs each "
            "pixel as it arrives and hands it to DMA, a memory-copy engine that writes into SRAM with no processor "
            "involved. The processor starts the capture, goes off to do other work, and gets told when the frame "
            "is done."),
          p("Before any of that, the camera has to be configured. It has a few dozen internal settings registers "
            "written over a two-wire bus called SCCB, which is the same as I2C, a standard two-wire chip-to-chip "
            "bus. The settings we write: reset, colour mode, output format, and 'shrink the picture by 4 in each "
            "direction'."),
          code("static const uint8_t k_ov7670_init[][2] = {\n"
               "    {0x12, 0x80},  // reset\n"
               "    {0x12, 0x14},  // colour (RGB) mode\n"
               "    {0x40, 0xD0},  // RGB565 pixel format\n"
               "    {0x0C, 0x04},  // enable the down-scaler\n"
               "    {0x72, 0x22},  // shrink by 4 in x and y  -> 160 x 120\n"
               "    {0x13, 0xE7},  // auto gain, auto white balance, auto exposure\n"
               "    ...\n};\n"
               "HAL_I2C_Master_Transmit(&hi2c1, 0x42, {reg, val}, 2, 100);   // one register per call"),
          Paragraph("4.1 Why 160 by 120 and what RGB565 means", H2),
          p("The camera can do 640 by 480, but that frame would be 600 KB, three times all our SRAM. We shrink to "
            "160 by 120. Each pixel comes as RGB565: 16 bits per pixel, with 5 bits of red, 6 of green, 5 of blue. "
            "That is 38 KB for a frame. The neural network wants normal 8-bit-per-colour pixels (RGB888), so after "
            "capture we expand each pixel from 16 bits to 24. The trick in the expansion is to copy the top bits into "
            "the empty bottom bits so that full white comes out as 255, not 248."),
          code("HAL_DCMI_Start_DMA(&hdcmi, DCMI_MODE_SNAPSHOT, (uint32_t)s_frame565, (CAM_W*CAM_H*2)/4);\n"
               "while (!s_frame_done)                       // set by the frame-complete interrupt\n"
               "    if (HAL_GetTick() - t0 > 500) return 0; // camera unplugged -> give up\n"
               "r5 = (p >> 11) & 0x1F;  g6 = (p >> 5) & 0x3F;  b5 = p & 0x1F;\n"
               "rgb888[3*i+0] = (r5 << 3) | (r5 >> 2);     // 5 bits -> 8 bits\n"
               "rgb888[3*i+1] = (g6 << 2) | (g6 >> 4);\n"
               "rgb888[3*i+2] = (b5 << 3) | (b5 >> 2);"),
          p("Memory so far: 38 KB raw frame plus 58 KB expanded frame. That leaves room for the 48 KB the neural "
            "network needs, and the rest for the program's own variables and stack.")]

# ================================================================== 5
story += [Paragraph("5. The vision: how the chip decides the lens is wet", H1),
          Paragraph("5.1 The idea: cut the picture into tiles and grade each tile", H2),
          p("We do not try to outline each drop. We cut the 160 by 120 picture into a grid of 48 by 48 pixel squares, "
            "a 3-wide by 2-high grid of six tiles, and ask one question per tile: 'water, or clean?' The fraction of "
            "tiles that say water is the coverage. Two of six tiles wet is 33 percent coverage. The wiper fires at "
            "5 percent or more, which for a 6-tile grid means any single tile."),
          p("This is a known approach from self-driving-car cameras (Valeo's SoilingNet papers), where it is called a "
            "coverage metric. It is cheap enough to run on a microcontroller because the network looks at one small "
            "tile at a time, and the grid also tells you where on the lens the water is."),
          Paragraph("5.2 What a neural network is, in this context", H2),
          p("A convolutional neural network (CNN) is a function that takes an image in and gives a score per class "
            "out. Inside it is a stack of layers. Each layer slides small filters across the image and produces a new, "
            "smaller image of 'features': edges first, then blobs, then things like 'a bright ring with a dark edge', "
            "which is what a water drop looks like. The numbers in the filters are the weights, and training means "
            "adjusting the weights until the scores are right on thousands of labelled example tiles. Once trained, "
            "running the network is just multiplications and additions, which a microcontroller can do."),
          Paragraph("5.3 Step 1: start from a published model instead of from zero", H2),
          p("Training from zero needs thousands of hand-labelled pictures of our lens, which we did not have. So I "
            "started from a model somebody had already trained on rain: Breckon's group at Durham published a small "
            "network in 2018 that looks at 30 by 30 patches from a car windshield camera and says drop or no drop, "
            "with 95 percent accuracy. They released the trained weights under an MIT licence."),
          p("Problem: the weights were saved in TensorFlow 1 with a library called TFLearn, both of which are dead. "
            "Nothing modern can load them. But the file is just a list of named arrays of numbers, and TensorFlow 2 "
            "can still read the raw arrays. So I rebuilt the same network layer by layer in Keras (the modern "
            "TensorFlow API) and copied each array into the matching layer by name, checking every shape:"),
          code("_NAME_MAP = {\"conv1\": \"Conv2D\", \"conv2\": \"Conv2D_1\", ..., \"fc3\": \"FullyConnected_2\"}\n"
               "reader = tf.train.load_checkpoint(tfl_path)       # opens the old TF1 file\n"
               "w = reader.get_tensor(f\"{scope}/W\")               # weights array\n"
               "b = reader.get_tensor(f\"{scope}/b\")               # bias array\n"
               "assert w.shape == layer.get_weights()[0].shape    # fail loudly if the port is wrong\n"
               "layer.set_weights([w, b])"),
          p("The network itself: five convolution layers (96 filters of 11x11, then 256 of 5x5, then 384, 384 and 256 "
            "of 3x3), with pooling layers between that shrink the image, then two dense layers of 4096 numbers each, "
            "then a 2-way output. To check the port, I ran the 16 sample patches that ship with their code and "
            "compared the answers."),
          Paragraph("5.4 Step 2: adapt it to our lens (fine-tuning)", H2),
          p("Their camera looked through a windshield a metre away. Ours is millimetres from the drops, so our drops "
            "are huge and blurry by comparison. A model trained on one does worse on the other. The fix is "
            "fine-tuning: keep the trained weights, then train a little more on pictures like ours so it adjusts."),
          p("For pictures like ours I used a public dataset, RaindropsOnWindshield: 8,190 frames where every drop has "
            "been outlined by hand (a mask), free to use with credit. A script cuts it into 30 by 30 patches. A patch "
            "counts as 'water' if at least 30 percent of it is inside a drop outline. It counts as 'clean' only if "
            "the patch and a one-patch border around it have no drop at all, so a drop edge never sneaks into a "
            "'clean' example and confuses the training. Frames from our own camera were added the same way. The "
            "split into training and test sets is by video clip, so the test never contains frames from a clip "
            "the model trained on, which would inflate the score."),
          code("# data_windshield.py -- cut labelled 30x30 patches from the mask images\n"
               "# positive: centred on a drop pixel, mask covers >= 30 % of the patch\n"
               "y0, x0 = drop_y - PATCH // 2, drop_x - PATCH // 2\n"
               "if mask[y0:y0+PATCH, x0:x0+PATCH].mean() >= 0.30:\n"
               "    pos.append(img[y0:y0+PATCH, x0:x0+PATCH])\n"
               "# negative: random spot, and the patch PLUS a one-patch border has no drop at all\n"
               "m = mask[max(0, y0-PATCH):y0+2*PATCH, max(0, x0-PATCH):x0+2*PATCH]\n"
               "if m.max() == 0:\n"
               "    neg.append(img[y0:y0+PATCH, x0:x0+PATCH])\n"
               "# split by video clip, not by frame\n"
               "rng.shuffle(sequences)\n"
               "train, val, test = sequences[:70%], sequences[70%:85%], sequences[85%:]\n"
               "# -> data/patches/{train,val,test}/{raindrop,non_raindrop}/*.png"),
          p("The fine-tuning itself is the standard recipe. First freeze the convolution layers and train only the "
            "dense layers at the end at a normal learning rate for a few rounds. Then unfreeze everything and train "
            "at a tiny learning rate, stopping as soon as the score on held-out data stops improving. Each training "
            "image is randomly flipped and rotated up to 45 degrees so the model does not memorise orientation."),
          code("# finetune.py\n"
               "aug = keras.Sequential([RandomFlip(\"horizontal_and_vertical\"), RandomRotation(0.125),  # +-45 deg\n"
               "                        RandomBrightness(0.15), RandomContrast(0.15)])\n"
               "\n"
               "# stage 1: only the dense head learns\n"
               "for layer in model.layers:\n"
               "    layer.trainable = layer.name.startswith(\"fc\")\n"
               "model.compile(keras.optimizers.Adam(1e-3), \"categorical_crossentropy\", metrics=[\"accuracy\"])\n"
               "model.fit(train_ds, validation_data=val_ds, epochs=5)\n"
               "\n"
               "# stage 2: everything learns, very gently, stop when validation stops improving\n"
               "for layer in model.layers:\n"
               "    layer.trainable = True\n"
               "model.compile(keras.optimizers.Adam(1e-5), \"categorical_crossentropy\", metrics=[\"accuracy\"])\n"
               "model.fit(train_ds, validation_data=val_ds, epochs=10,\n"
               "          callbacks=[EarlyStopping(patience=3, restore_best_weights=True)])\n"
               "test = model.evaluate(test_ds, return_dict=True)   # written to finetune_report.json"),
          Paragraph("5.5 Step 3: shrink it 900 times (distillation)", H2),
          p("Here is the wall. Count the weights: those two dense layers are 256 by 4096 and 4096 by 4096. Together "
            "with the rest that is about 18 million numbers. In 4-byte floats that is 75 MB. Even squeezed to 1 byte "
            "each it is 19 MB. Our chip has 512 KB of flash. The big model cannot go on the chip, full stop. It also "
            "uses one layer type (local response normalization) that the chip-side library does not support."),
          p("So the big model does not go on the chip. It becomes the teacher. I designed a tiny student network that "
            "does fit, and trained the student to copy the teacher. This is knowledge distillation. Instead of only "
            "telling the student 'this tile is water', you show it the teacher's full opinion, like '80 percent "
            "water, 20 percent clean'. Those soft answers carry much more information per example, including what "
            "the teacher learned about hard cases like glare, which is exactly where our first detector failed."),
          p("The student: input is a 48 by 48 tile. A first small convolution, then five 'depthwise separable' blocks, "
            "a MobileNet trick that does a cheap per-channel filter followed by a cheap 1x1 mixing filter instead of "
            "one expensive full filter, which cuts the maths by about 8 times. Then average everything down to one "
            "vector and a final layer that outputs two scores. About 20,000 weights total. Every layer type is one "
            "the chip-side library supports."),
          code("x = conv3x3_stride2(inp, 16)            # 48x48 -> 24x24\n"
               "x = ds_block(x, 32, stride=2); x = ds_block(x, 32, 1)   # -> 12x12\n"
               "x = ds_block(x, 64, stride=2); x = ds_block(x, 64, 1)   # -> 6x6\n"
               "x = ds_block(x, 128, stride=2)          # -> 3x3\n"
               "x = GlobalAveragePooling2D()(x)         # 3x3x128 -> 128 numbers\n"
               "out = Dense(2)(x)                       # score for clean, score for water\n"
               "\n"
               "# the distillation loss, per batch:\n"
               "loss = 0.7 * KL(teacher_soft, student_soft) * T**2 + 0.3 * CrossEntropy(true_label, student)\n"
               "# T = 4 'softens' the teacher's answers so the small differences show through"),
          Paragraph("5.6 Step 4: turn floats into 8-bit integers (quantization)", H2),
          p("Trained weights are 32-bit floating point numbers. Microcontrollers are slow at floating point and flash "
            "is small, so we convert the whole network to 8-bit integers. Each weight becomes a number from -128 to "
            "127 plus one shared scale factor per layer that says what one step is worth. Same for the numbers "
            "flowing between layers at run time. That is 4 times smaller and several times faster, and on a "
            "network this size it costs almost no accuracy."),
          p("To pick the scale factors for the run-time numbers, the converter needs to see typical inputs. You hand "
            "it a 'representative dataset', a few hundred real tiles, and it runs them through and records how big "
            "each layer's numbers get. I use tiles from the validation set, not the training set, so the scales are "
            "not tuned to the exact images the weights were fitted on. The output is a .tflite file, plus that "
            "file dumped as a C array so it compiles straight into the firmware."),
          code("conv = tf.lite.TFLiteConverter.from_keras_model(student)\n"
               "conv.optimizations = [tf.lite.Optimize.DEFAULT]\n"
               "conv.representative_dataset = lambda: (([x[None]],) for x in val_tiles)\n"
               "conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]\n"
               "conv.inference_input_type = conv.inference_output_type = tf.int8\n"
               "open(\"raindrop_student_int8.tflite\", \"wb\").write(conv.convert())\n"
               "# then: alignas(16) const unsigned char g_raindrop_student[] = { 0x1c, 0x00, ... };"),
          Paragraph("5.7 Step 5: run it on the chip (TensorFlow Lite Micro)", H2),
          p("TensorFlow Lite Micro (TFLM) is a small C++ library that runs .tflite models on microcontrollers with no "
            "operating system and no dynamic memory. You give it the model bytes, a list of which layer types to "
            "compile in (we register only the six we use, to save flash), and a fixed block of memory called the "
            "arena where it keeps all the intermediate results. Ours is 48 KB. At boot:"),
          code("g_model = tflite::GetModel(g_raindrop_student);          // point at the array in flash\n"
               "g_resolver.AddConv2D(); g_resolver.AddDepthwiseConv2D(); g_resolver.AddMean();\n"
               "g_resolver.AddFullyConnected(); g_resolver.AddReshape(); g_resolver.AddSoftmax();\n"
               "static tflite::MicroInterpreter interp(g_model, g_resolver, g_arena, 48 * 1024);\n"
               "interp.AllocateTensors();                                 // carve up the arena once\n"
               "g_in = interp.input(0); g_out = interp.output(0);"),
          p("Per frame, the code walks the 3 by 2 grid. For each tile it copies the 48 rows out of the big frame "
            "into a small buffer, converts each pixel byte into the network's int8 input using the scale and "
            "zero-point that the converter stored inside the model, runs the network, and reads the two output "
            "scores. Whichever score is bigger wins; there is no need to convert back to real probabilities, "
            "because the comparison works directly on the integers."),
          code("// the network was trained on pixel/255, so:\n"
               "q = round((pixel / 255) / input_scale) + input_zero_point;   clamp to [-128, 127]\n"
               "g_in->data.int8[i] = q;\n"
               "...\n"
               "g_interp->Invoke();\n"
               "raindrop = g_out->data.int8[1] > g_out->data.int8[0];\n"
               "hits += raindrop;\n"
               "return (float)hits / (rows * cols);     // coverage, 0.0 to 1.0"),
          p("A hardware cycle counter inside the processor (the DWT) times each pass. The count is printed on the "
            "status line, which is where our per-frame timing numbers came from.")]

# ================================================================== 6
story += [PageBreak(), Paragraph("6. Putting it together: the main loop", H1),
          p("Everything above is called from one loop that runs once per second. Read it top to bottom and you have "
            "the whole product."),
          code("for (;;) {\n"
               "    uint32_t t0 = HAL_GetTick();\n"
               "\n"
               "    // 1. temperature -> heater\n"
               "    float temp_c = ReadTemperatureC();\n"
               "    int heat = temp_c < HEATER_THRESH_C;\n"
               "    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, heat ? GPIO_PIN_RESET : GPIO_PIN_SET);\n"
               "\n"
               "    // 2-3. picture -> neural network -> coverage\n"
               "    float cover = -1.0f;\n"
               "    if (cam_ok && nn_ok && CameraCaptureRGB888(s_frame))\n"
               "        cover = RaindropCoverage(s_frame, CAM_W, CAM_H, s_grid);\n"
               "\n"
               "    // 4. coverage -> wiper, with two safety rules\n"
               "    if (cover >= WIPE_THRESHOLD && temp_c > 0.0f && HAL_GetTick() - last_wipe > WIPE_COOLDOWN_MS) {\n"
               "        Wipe();\n"
               "        last_wipe = HAL_GetTick();\n"
               "    }\n"
               "\n"
               "    // 5. one line of log per second\n"
               "    printf(\"T=%.1fC heat=%d cover=%.2f grid=%s nn_us=%lu\\r\\n\", temp_c, heat, cover, grid, nn_us);\n"
               "    HAL_Delay(LOOP_PERIOD_MS - (HAL_GetTick() - t0));\n"
               "}"),
          p("The two safety rules on the wiper: it never runs at or below 0 C, because a wiper dragging over ice "
            "strips the blade and stalls the servo, and it never runs again within 4 seconds, because one sweep "
            "takes 3.7 seconds and the next frame would still see the wet lens mid-wipe and fire again."),
          p("If the camera or the model fails to start, the loop keeps running the heater and prints the failure. "
            "During development it could also fall back to the laptop sending START over the cable."),
          Paragraph("6.1 Where the memory goes", H2),
          table([["Buffer", "Size", "Why"],
                 [cell("Raw RGB565 camera frame"), cell("38 KB"), cell("DMA writes here")],
                 [cell("Expanded RGB888 frame"), cell("58 KB"), cell("what the network reads")],
                 [cell("TFLM arena"), cell("48 KB"), cell("all intermediate layer outputs")],
                 [cell("Model (in flash, not SRAM)"), cell("about 25 KB"), cell("the int8 weights")],
                 [cell("Total SRAM"), cell("about 150 KB of 192 KB"), cell("rest is stack and HAL state")]],
                [2.2 * inch, 1.6 * inch, 2.9 * inch]),
          Spacer(1, 4),
          Paragraph("6.2 Building it", H2),
          p("In STM32CubeIDE, turn on DCMI, a DMA stream for it, I2C1, and a clock output for the camera in the .ioc "
            "file and let CubeMX generate the setup code. Pull the TensorFlow Lite Micro sources in as a folder "
            "(there is a script in their repo, create_tflm_tree.py, that produces exactly the files you need) and "
            "compile them as C++17. Add the three firmware files and the generated model array. Swap the old "
            "main.c for main_raindrop.c. Flash and open the serial port.")]

# ================================================================== 7
story += [Paragraph("7. How we got here: the earlier detector and what it taught us", H1),
          p("The first detector was not a neural network. It was a quick OpenCV pipeline on the laptop, written to "
            "get something moving. OpenCV is a standard image library. The idea: water on glass looks grey, so "
            "convert the picture to HSV (hue, saturation, value: colour, how colourful, how bright), keep pixels "
            "that are not colourful (saturation under 40) and not dark (value over 100), fill the little gaps to "
            "make solid blobs, draw circles around the biggest blobs, and count what fraction of the picture is "
            "inside them. Over 5 percent, send START down the cable."),
          code("_, s_mask = cv2.threshold(s, 40, 255, cv2.THRESH_BINARY_INV)     # low saturation\n"
               "_, v_mask = cv2.threshold(v, 100, 255, cv2.THRESH_BINARY)        # not dark\n"
               "closed = cv2.morphologyEx(cv2.bitwise_and(s_mask, v_mask), cv2.MORPH_CLOSE, kernel)\n"
               "contours = sorted(cv2.findContours(closed, ...)[0], key=cv2.contourArea, reverse=True)\n"
               "for c in contours[1:3]: cv2.circle(...)  # skip the biggest (lens ring), fill next two\n"
               "if black_percent > 5: ser.write(b\"START\")"),
          p("It worked on clean test pictures and failed in the enclosure: glare, scratches and surface texture all "
            "got flagged as water. Our TA found the real reason by looking at the hardware, not the code: the "
            "camera is so close to the surface where drops form that it is effectively zoomed way in, and tiny "
            "texture becomes big blobs. No threshold fixes that. You need something that has learned what a drop "
            "looks like versus what glare looks like. That is the whole reason for the neural network path, and "
            "why distillation from a teacher that had seen lots of glare mattered."),
          p("The 5 percent rule survived from the heuristic into the final product. Everything else was replaced.")]

# ================================================================== 8
story += [Paragraph("8. How we tested it", H1),
          bullets([
              "<b>Detection accuracy: 89 percent.</b> 100 test images of rain and ice on the lens in different "
              "lighting. For each, the chip's printed tile grid was compared with what was actually on the lens.",
              "<b>Each part alone first.</b> Regulators on a meter (5 V and 3.3 V). MOSFET output with and without gate "
              "drive. Servo on a servo tester at the machine shop, which is how we found one motor was simply dead. "
              "Temperature against a real thermometer, which gave us the 9 C offset. PWM on a scope.",
              "<b>The model pipeline.</b> Every stage writes a report file: did every weight array match on the port, "
              "how did the sample patches score, test accuracy after fine-tuning, student test accuracy after "
              "distillation, and how often int8 agrees with the float model after quantization. A separate "
              "PyTorch pipeline in the repo (lens_soiling/) has nine automated tests as a fallback.",
              "<b>Everything together.</b> Final demo with all subsystems triggering each other: an ice cooler and the "
              "20.5 C threshold for the heater, water on the lens for the wiper, LED confirming heater state. "
              "Then two hours outdoors.",
          ])]

# ================================================================== 9
story += [Paragraph("9. What went wrong and what we did", H1),
          table([
              ["Problem", "Why", "What we did"],
              [cell("First detector flagged glare as water"),
               cell("Lens millimetres from the wet surface magnifies texture"),
               cell("Replaced it with a learned tile classifier; distilled from a teacher that had seen glare")],
              [cell("Published model far too big for the chip"), cell("18 M weights; uses a layer TFLM lacks"),
               cell("Kept it as the teacher; distilled a 20 k-weight student")],
              [cell("Published weights would not load"), cell("Saved by dead TF1 / TFLearn"),
               cell("Read the raw arrays, rebuilt the network in Keras, copied by name")],
              [cell("Frame plus model did not fit memory"), cell("192 KB SRAM"),
               cell("160x120 frames, 48 KB arena, only six layer types compiled in")],
              [cell("Second PCB's chip destroyed"), cell("0.5 mm pin pitch, hand soldering"),
               cell("Ran the same firmware on the Nucleo dev board")],
              [cell("Servo would not move"), cell("Dead motor"), cell("Proved it on a servo tester, replaced it")],
              [cell("Could not test freezing indoors"), cell("Ice cooler tops out around 15 C"),
               cell("Raised the heater threshold to 20.5 C for the demo")],
          ], [2.0 * inch, 2.2 * inch, 2.5 * inch])]

# ================================================================== 10
story += [Paragraph("10. If someone asks", H1),
          bullets([
              "<b>Why tiles instead of finding each drop?</b> Cheaper by far, fits a microcontroller, and the wipe "
              "decision only needs 'how much', not 'what shape'.",
              "<b>Why not train your own small model from scratch?</b> No big labelled dataset of our lens. The "
              "teacher had already learned rain and glare from thousands of images; distillation moves that into "
              "the student for free.",
              "<b>Why does the heater ignore the camera?</b> Frost, fog, and dirt look alike. Temperature does not lie.",
              "<b>Hardest bug?</b> The glare false positives. The fix came from looking at the mechanical setup, not "
              "the code.",
              "<b>What would you change?</b> Mount the camera further from the wet surface. Add a frost class to the "
              "student. Use an STM32H7 with more memory for a full-size frame and a bigger student.",
          ]),
          Spacer(1, 10),
          Paragraph("References: Guo, Akcay, Adey, Breckon, ICIP 2018 (github.com/tobybreckon/raindrop-detection-cnn). "
                    "Soboleva & Shipitko, RaindropsOnWindshield, 2021 (Zenodo 4680442). Uricar et al., SoilingNet, "
                    "ITSC 2019. Hinton, Vinyals, Dean, Distilling the Knowledge in a Neural Network, 2015. "
                    "Howard et al., MobileNets, 2017. Code: Weather-Resistant-Camera/CNN/ and main.c.", SMALL)]

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                        topMargin=0.8 * inch, bottomMargin=0.8 * inch, title="Adaptive Camera Cleaning System",
                        author="Deyvik Bhan")
doc.build(story)
print(OUT)
