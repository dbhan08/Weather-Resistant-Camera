import cv2
import numpy as np
import time
import serial

def run_motor():
    ser = serial.Serial('COM3', baudrate=115200, timeout=1)

    ser.write(b"START")
    response = ser.readline().decode().strip()
    print(f"STM32 responded: {response}")

    #time.sleep(2)

    #ser.write(b"STOPP")
    #response = ser.readline().decode().strip()
    #print(f"STM32 responded: {response}")

    ser.close()
    return

def mask_drop_hsv(img):
    # Convert to HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # Thresholds on Saturation and Value
    _, s_mask = cv2.threshold(s, 40, 255, cv2.THRESH_BINARY_INV)
    _, v_mask = cv2.threshold(v, 100, 255, cv2.THRESH_BINARY)

    combined = cv2.bitwise_and(s_mask, v_mask)

    # Morphological closing to fill blobs
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15,15))
    closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    closed_with_circles = closed.copy()
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    # Draw on largest two drops (excluding the biggest contour)
    for c in contours[1:3]:
        (x, y), r = cv2.minEnclosingCircle(c)
        center = (int(x), int(y))
        radius = int(r)
        cv2.circle(closed_with_circles, center, radius, 0, thickness=2)
        cv2.circle(closed_with_circles, center, radius, 0, thickness=-1)

    total_pixels = closed_with_circles.size
    black_pixels = np.sum(closed_with_circles == 0)
    black_percent = (black_pixels / total_pixels) * 100

    if black_percent>5:
        run_motor()


    print(f"Black pixel coverage: {black_percent:.2f}%")

    # Show result
    cv2.imshow('Processed', closed_with_circles)
    cv2.imwrite("final_image.jpg", closed_with_circles)

    cv2.waitKey(1)

def main_loop():
    cap = cv2.VideoCapture(1)  # Change to 1 or 2 if needed
    #print(cap)


    if not cap.isOpened():
        print("Cannot open camera")
        return

    try:
        while True:
            ret, frame = cap.read()
            frame = cv2.flip(frame, 0)  # Flip vertically

            if not ret:
                print("Failed to grab frame")
                break

            # Optional: show the raw frame
            cv2.imshow("Live", frame)
            cv2.imwrite("initial_image.jpg", frame)

            # Process snapshot
            mask_drop_hsv(frame)

            # Wait 5 seconds
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            time.sleep(4)

    except KeyboardInterrupt:
        print("Stopped by user.")

    finally:
        cap.release()
        cv2.destroyAllWindows()




if __name__ == '__main__':
    main_loop()


#run_motor()


