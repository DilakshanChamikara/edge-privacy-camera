#!/usr/bin/env python3

import cv2
import os
import numpy as np
from datetime import datetime
from picamera2 import Picamera2
import time

from crypto_utils import get_session_key, encrypt_data_to_file


def create_folder():
    folder_path = os.path.join("facedata", "camcap")
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


def capture_photos():
    enc_key = get_session_key()
    folder = create_folder()

    picam2 = Picamera2()
    preview_size = (1280, 720)
    picam2.configure(picam2.create_preview_configuration(
        main={"format": 'XRGB8888', "size": preview_size}
    ))
    picam2.start()
    time.sleep(2)

    cv2.namedWindow('Capture', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Capture', *preview_size)

    photo_count = 0

    print("Taking photos. Press SPACE to capture, 'q' to quit.")
    print(f"Encrypted photos will be saved in: {folder}")
    print(f"Preview resolution: {preview_size[0]}x{preview_size[1]}")

    while True:
        frame = picam2.capture_array()
        display = frame.copy()

        h, w = display.shape[:2]
        text1 = "SPACE: Capture"
        text2 = "Q: Quit"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 1
        color = (0, 0, 255)  # red

        (tw1, th1), _ = cv2.getTextSize(text1, font, font_scale, thickness)
        (tw2, th2), _ = cv2.getTextSize(text2, font, font_scale, thickness)

        margin = 10
        x1 = w - tw1 - margin
        y1 = margin + th1
        x2 = w - tw2 - margin
        y2 = margin + th1 + th2 + 5

        cv2.putText(display, text1, (x1, y1), font, font_scale,
                    color, thickness, cv2.LINE_AA)
        cv2.putText(display, text2, (x2, y2), font, font_scale,
                    color, thickness, cv2.LINE_AA)

        cv2.imshow('Capture', display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' '):
            photo_count += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            enc_filepath = os.path.join(folder, f"{timestamp}.jpg.enc")

            # encode to jpeg in memory, encrypt, write
            success, jpg_buffer = cv2.imencode('.jpg', frame)
            if success:
                encrypt_data_to_file(jpg_buffer.tobytes(), enc_filepath, enc_key)
                print(f"Photo {photo_count} saved (encrypted): {enc_filepath}")
            else:
                print(f"[ERROR] Failed to encode photo {photo_count}")

        elif key == ord('q'):
            break

    cv2.destroyAllWindows()
    picam2.stop()
    print(f"Photo capture completed. {photo_count} encrypted photos saved in {folder}.")


if __name__ == "__main__":
    capture_photos()
