"""Pretrained path: port Breckon's AlexNet-30^2 raindrop classifier
(TFLearn / TF1 checkpoint) to Keras, quantize it to TFLite, and distill it
into a microcontroller-sized student.  See ../README.md.

Not executed in this repo's CI: it needs TensorFlow plus the Durham
Collections weight download.  Every script prints what it did and writes a
JSON report so results can be checked when it is run.
"""
