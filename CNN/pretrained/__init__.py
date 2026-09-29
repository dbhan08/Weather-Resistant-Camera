"""Pretrained path: port Breckon's AlexNet-30^2 raindrop classifier
(TFLearn / TF1 checkpoint) to Keras, quantize it to TFLite, and distill it
into a microcontroller-sized student.  See ../README.md.

Needs TensorFlow plus the Durham Collections weight download, so it is not
part of the pytest suite.  Every script writes a JSON report so results
are recorded when it runs.
"""
