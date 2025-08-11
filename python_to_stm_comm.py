import serial
import time


ser = serial.Serial('COM3', baudrate=115200, timeout=1)

ser.write(b"START")
response = ser.readline().decode().strip()
print(f"STM32 responded: {response}")

time.sleep(2)

ser.write(b"STOPP")
response = ser.readline().decode().strip()
print(f"STM32 responded: {response}")

ser.close()

