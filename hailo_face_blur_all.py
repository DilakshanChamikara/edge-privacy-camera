#!/usr/bin/env python3

import argparse
import time

import cv2
import numpy as np

# test fps
fps_log = []

from hailo_utils import (
    SCRFD_HEF, SCRFD_INPUT_SIZE,
    HailoEngine, SCRFDPostProcessor, CentroidTracker,
    GracefulCamera, VideoRecorder, FrameSkipDetector,
    blur_face, draw_box, draw_hud
)
from crypto_utils import get_session_key
from hailo_enroll import enroll_if_needed


def main():
    ap = argparse.ArgumentParser(description="Blur ALL faces (Hailo-10H)")
    ap.add_argument("--score-thresh", type=float, default=0.5)
    ap.add_argument("--nms-thresh", type=float, default=0.4)
    ap.add_argument("--detect-interval", type=int, default=2)
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--record-path", type=str, default=None)
    args = ap.parse_args()

    key = get_session_key()
    enroll_if_needed(key)

    print("[INFO] Loading SCRFD face detection on Hailo...")
    scrfd = HailoEngine(SCRFD_HEF)
    scrfd_post = SCRFDPostProcessor(
        SCRFD_INPUT_SIZE, args.score_thresh, args.nms_thresh)

    tracker = CentroidTracker()
    skipper = FrameSkipDetector(detect_interval=args.detect_interval)
    fc, ft, fps = 0, time.time(), 0.0

    print("[INFO] Starting camera...")
    camera = GracefulCamera()

    recorder = None
    if not args.no_record:
        recorder = VideoRecorder(base_path=args.record_path)

    print("[INFO] Running - blurring ALL faces. Press 'q' to quit.")

    try:
        while True:
            frame = camera.capture()
            if frame is None:
                print("[WARNING] Skipping frame (camera returned none)")
                time.sleep(0.1)
                continue

            if skipper.should_detect():
                inp = cv2.resize(frame, (SCRFD_INPUT_SIZE, SCRFD_INPUT_SIZE))
                inp = cv2.cvtColor(inp, cv2.COLOR_BGRA2RGB).astype(np.float32)
                try:
                    dets = scrfd_post(scrfd.infer(inp))
                except Exception as e:
                    print(f"[WARNING] Detection error: {e}")
                    dets = []
                skipper.store_detections(dets)
            else:
                dets = skipper.get_interpolated()

            bboxes = [d["bbox"] for d in dets]
            labels = ["Face"] * len(dets)
            colors = [(0, 0, 255)] * len(dets)  # red
            tracked = tracker.update(bboxes, labels, colors)

            display = frame.copy()
            for _, (top, right, bottom, left), label, color in tracked:
                blur_face(display, top, right, bottom, left)
                draw_box(display, top, right, bottom, left, label, color)

            # fps counter
            fc += 1
            if time.time() - ft > 1:
                fps = fc / (time.time() - ft)
                fps_log.append(fps)
                fc, ft = 0, time.time()
                print(f"FPS: {fps:.1f}")

            draw_hud(display, fps, recording=(recorder is not None))

            if recorder:
                recorder.write_frame(display)

            cv2.imshow("Blur ALL Faces", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        # test fps
        # if fps_log:
        #     print(f"\nFPS RESULTS")
        #     print(f"Average: {np.mean(fps_log):.1f}")
        #     print(f"Min:     {np.min(fps_log):.1f}")
        #     print(f"Max:     {np.max(fps_log):.1f}")

        camera.stop()
        if recorder:
            recorder.stop()
        cv2.destroyAllWindows()
        print("[INFO] Done.")


if __name__ == "__main__":
    main()
