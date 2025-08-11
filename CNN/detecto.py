import cv2, numpy as np, argparse

def mask_drop_hsv(image_path):
    # 1) load + HSV split
    img = cv2.imread(image_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # 1️⃣ Saturation channel

    # 2️⃣ threshold S to get low‑sat regions (drops)
    _, s_mask = cv2.threshold(s, 40, 255, cv2.THRESH_BINARY_INV)

    # 3️⃣ Value channel

    # 4️⃣ threshold V to remove very dark shadows
    _, v_mask = cv2.threshold(v, 100, 255, cv2.THRESH_BINARY)

    # 5️⃣ combine S and V masks
    combined = cv2.bitwise_and(s_mask, v_mask)

    # 6️⃣ morph close to fill the drop blob
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15,15))
    closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    closed_with_circles = closed.copy()
    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    # skip the large ring, take the next two drops
    for c in contours[1:3]:
        (x, y), r = cv2.minEnclosingCircle(c)
        center = (int(x), int(y))
        radius = int(r)

        # outline in black
        cv2.circle(closed_with_circles, center, radius, 0, thickness=2)
        # fill the interior too
        cv2.circle(closed_with_circles, center, radius, 0, thickness=-1)

    cv2.imshow('6️⃣ closed + circles', closed_with_circles)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('-i','--image', required=True, help='path to input image')
    args = p.parse_args()
    mask_drop_hsv(args.image)