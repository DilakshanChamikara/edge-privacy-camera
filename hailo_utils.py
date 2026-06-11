#!/usr/bin/env python3

import os
import sys
import time
import pickle
import json
from collections import OrderedDict
from datetime import datetime

import cv2
import numpy as np

try:
    from hailo_platform import (
        HEF, VDevice, InferVStreams,
        ConfigureParams, HailoStreamInterface,
        InputVStreamParams, OutputVStreamParams,
        FormatType
    )
except ImportError:
    print("[ERROR] hailo_platform not found. Install: sudo apt install hailo-all")
    sys.exit(1)

# paths
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR    = os.path.join(SCRIPT_DIR, "models")
ENCODINGS_DIR = os.path.join(SCRIPT_DIR, "encodings")
FACEDATA_DIR  = os.path.join(SCRIPT_DIR, "facedata")
CONFIG_DIR    = os.path.join(SCRIPT_DIR, "config")

SCRFD_HEF   = os.path.join(MODELS_DIR, "scrfd_2.5g.hef")
ARCFACE_HEF = os.path.join(MODELS_DIR, "arcface_mobilefacenet.hef")

VIDEO_W, VIDEO_H = 1280, 720
SCRFD_INPUT_SIZE = 640


def get_recording_path():
    # check env var
    env_path = os.environ.get("RECORDING_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path

    # check config
    settings_file = os.path.join(CONFIG_DIR, "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file) as f:
                p = json.load(f).get("recording_path", "")
            if p and os.path.isdir(p):
                return p
        except Exception:
            pass

    # auto-detect external drive
    for root_dir in ["/media", "/mnt"]:
        if not os.path.isdir(root_dir):
            continue
        for user_dir in os.listdir(root_dir):
            user_path = os.path.join(root_dir, user_dir)
            if not os.path.isdir(user_path):
                continue
            for drive in os.listdir(user_path):
                drive_path = os.path.join(user_path, drive)
                if os.path.isdir(drive_path) and os.access(drive_path, os.W_OK):
                    rec_dir = os.path.join(drive_path, "cctv_recordings")
                    os.makedirs(rec_dir, exist_ok=True)
                    return rec_dir

    # fallback to local
    fallback = os.path.join(SCRIPT_DIR, "recordings")
    os.makedirs(fallback, exist_ok=True)
    print(f"[WARNING] No external drive found. Recording to: {fallback}")
    return fallback


class HailoEngine:
    _shared_vdevice = None

    @classmethod
    def _get_vdevice(cls):
        if cls._shared_vdevice is None:
            cls._shared_vdevice = VDevice()
        return cls._shared_vdevice

    @classmethod
    def release(cls):
        if cls._shared_vdevice is not None:
            try:
                cls._shared_vdevice.release()
            except Exception:
                pass
            cls._shared_vdevice = None

    def __init__(self, hef_path, max_retries=3):
        if not os.path.exists(hef_path):
            print(f"[ERROR] HEF not found: {hef_path}")
            sys.exit(1)
        self._hef_path = hef_path
        self._max_retries = max_retries
        self._connect()

    def _connect(self):
        self.vdevice = self._get_vdevice()
        self.model = self.vdevice.create_infer_model(self._hef_path)
        self.input_name = self.model.input().name
        self.input_shape = self.model.input().shape
        self.model.input().set_format_type(FormatType.UINT8)
        self._output_names = list(self.model.output_names)
        self._output_shapes = {}
        for name in self._output_names:
            out = self.model.output(name)
            out.set_format_type(FormatType.FLOAT32)
            self._output_shapes[name] = list(out.shape)
        self.configured = self.model.configure()
        print(f"[INFO] HEF loaded: {os.path.basename(self._hef_path)}, "
              f"input={self.input_shape}, outputs={len(self._output_names)}")
        for name in self._output_names:
            print(f"  -> {name}: {self._output_shapes[name]}")

    def infer(self, data):
        if data.dtype != np.uint8:
            data = np.clip(data, 0, 255).astype(np.uint8)
        if data.ndim == 3:
            data = data[np.newaxis]
        for attempt in range(self._max_retries):
            try:
                bindings = self.configured.create_bindings()
                bindings.input().set_buffer(data)
                output_buffers = {}
                for name in self._output_names:
                    shape = self._output_shapes[name]
                    buf = np.empty([data.shape[0]] + shape, dtype=np.float32)
                    bindings.output(name).set_buffer(buf)
                    output_buffers[name] = buf
                self.configured.run([bindings], 10000)
                return output_buffers
            except Exception as e:
                print(f"[WARNING] Hailo error (attempt {attempt+1}/{self._max_retries}): {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(0.5)
                    try:
                        HailoEngine._shared_vdevice = None
                        self._connect()
                    except Exception as re_err:
                        print(f"[WARNING] Reconnect failed: {re_err}")
                else:
                    raise RuntimeError(f"Hailo failed after {self._max_retries} attempts")


class GracefulCamera:
    def __init__(self, width=VIDEO_W, height=VIDEO_H, fps=30, max_retries=5):
        self.width = width
        self.height = height
        self.fps = fps
        self.max_retries = max_retries
        self.picam2 = None
        self._start()

    def _start(self):
        from picamera2 import Picamera2
        if self.picam2 is not None:
            try:
                self.picam2.stop()
            except Exception:
                pass
        self.picam2 = Picamera2()
        self.picam2.configure(self.picam2.create_preview_configuration(
            main={"format": "XRGB8888", "size": (self.width, self.height)},
            controls={"FrameRate": self.fps},
        ))
        self.picam2.start()
        time.sleep(1)
        print(f"[INFO] Camera started: {self.width}x{self.height}@{self.fps}fps")

    def capture(self):
        for attempt in range(self.max_retries):
            try:
                frame = self.picam2.capture_array()
                if frame is not None and frame.size > 0:
                    return frame
                raise ValueError("Empty frame")
            except Exception as e:
                print(f"[WARNING] Camera error ({attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(0.5)
                    try:
                        self._start()
                    except Exception:
                        time.sleep(1)
        print("[ERROR] Camera unrecoverable.")
        return None

    def stop(self):
        if self.picam2:
            try:
                self.picam2.stop()
            except Exception:
                pass
            self.picam2 = None


class VideoRecorder:
    def __init__(self, base_path=None, rotation_minutes=30,
                 fps=15.0, codec="XVID"):
        self.base_path = base_path or get_recording_path()
        self.rotation_minutes = rotation_minutes
        self.fps = fps
        self.codec = codec
        self.writer = None
        self.current_file = None
        self.segment_start = None
        self.frame_count = 0
        os.makedirs(self.base_path, exist_ok=True)
        print(f"[INFO] Recording to: {self.base_path} "
              f"(rotate every {rotation_minutes}min)")

    def _new_segment(self, width, height):
        self._close_writer()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_dir = os.path.join(self.base_path, datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(date_dir, exist_ok=True)
        self.current_file = os.path.join(date_dir, f"blurred_{ts}.avi")
        fourcc = cv2.VideoWriter_fourcc(*self.codec)
        self.writer = cv2.VideoWriter(
            self.current_file, fourcc, self.fps, (width, height))
        if not self.writer.isOpened():
            print(f"[ERROR] Failed to open writer: {self.current_file}")
            self.writer = None
            return
        self.segment_start = time.time()
        self.frame_count = 0
        print(f"[INFO] New recording segment: {self.current_file}")

    def _close_writer(self):
        if self.writer is not None:
            self.writer.release()
            if self.frame_count > 0:
                print(f"[INFO] Segment closed: {os.path.basename(self.current_file)} "
                      f"({self.frame_count} frames)")
            self.writer = None

    def write_frame(self, blurred_frame):
        h, w = blurred_frame.shape[:2]
        if (self.writer is None or
                time.time() - self.segment_start > self.rotation_minutes * 60):
            self._new_segment(w, h)
        if self.writer is None:
            return
        if blurred_frame.shape[2] == 4:
            bgr = cv2.cvtColor(blurred_frame, cv2.COLOR_BGRA2BGR)
        else:
            bgr = blurred_frame
        self.writer.write(bgr)
        self.frame_count += 1

    def stop(self):
        self._close_writer()
        print("[INFO] Recording stopped.")


class FrameSkipDetector:
    def __init__(self, detect_interval=2):
        self.detect_interval = detect_interval
        self.frame_count = 0
        self.prev_dets = []
        self.prev_prev_dets = []

    def should_detect(self):
        self.frame_count += 1
        return (self.frame_count % self.detect_interval) == 0

    def store_detections(self, dets):
        self.prev_prev_dets = self.prev_dets
        self.prev_dets = dets

    def get_interpolated(self):
        if not self.prev_dets:
            return []
        if not self.prev_prev_dets or len(self.prev_dets) != len(self.prev_prev_dets):
            return self.prev_dets
        interpolated = []
        for curr, prev in zip(self.prev_dets, self.prev_prev_dets):
            ct, pt = curr["bbox"], prev["bbox"]
            new_bbox = tuple(int(c + (c - p) * 0.3) for c, p in zip(ct, pt))
            interpolated.append({
                "bbox": new_bbox,
                "score": curr["score"],
                "landmarks": curr.get("landmarks"),
            })
        return interpolated


class SCRFDPostProcessor:
    STEPS = [8, 16, 32]

    def __init__(self, input_size=640, score_thresh=0.5, nms_thresh=0.4,
                 output_w=VIDEO_W, output_h=VIDEO_H):
        self.input_size = input_size
        self.score_thresh = score_thresh
        self.nms_thresh = nms_thresh
        self.output_w = output_w
        self.output_h = output_h
        self._anchors_cache = {}

    def _gen_anchors(self, n_per_level):
        if n_per_level in self._anchors_cache:
            return self._anchors_cache[n_per_level]
        anchors = []
        for stride in self.STEPS:
            h = w = self.input_size // stride
            grid = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
            centers = (grid * stride).reshape(-1, 2) / self.input_size
            if n_per_level > 1:
                centers = np.tile(centers[:, None, :], (1, n_per_level, 1)).reshape(-1, 2)
            scales = np.ones_like(centers) * stride / self.input_size
            anchors.append(np.concatenate([centers, scales], axis=1))
        result = np.concatenate(anchors, axis=0)
        self._anchors_cache[n_per_level] = result
        return result

    def _decode_boxes(self, raw, anc):
        return np.stack([
            anc[:, 0] - raw[:, 0] * anc[:, 2],
            anc[:, 1] - raw[:, 1] * anc[:, 3],
            anc[:, 0] + raw[:, 2] * anc[:, 2],
            anc[:, 1] + raw[:, 3] * anc[:, 3],
        ], axis=-1)

    def _decode_kps(self, raw, anc):
        pts = []
        for i in range(0, 10, 2):
            pts.append(anc[:, 0] + raw[:, i] * anc[:, 2])
            pts.append(anc[:, 1] + raw[:, i + 1] * anc[:, 3])
        return np.stack(pts, axis=-1)

    def _nms(self, boxes, scores):
        x1, y1, x2, y2 = boxes.T
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[np.where(iou <= self.nms_thresh)[0] + 1]
        return keep

    def _classify_layers(self, outputs):
        cls_l, box_l, kps_l = [], [], []
        for name, tensor in outputs.items():
            if tensor.ndim == 4:
                tensor = tensor[0]
            c = tensor.shape[-1]
            sp = tensor.shape[0] * tensor.shape[1] if tensor.ndim == 3 else tensor.size // c
            if c in (1, 2):    cls_l.append((name, tensor, sp, c))
            elif c in (4, 8):  box_l.append((name, tensor, sp, c))
            elif c in (10, 20): kps_l.append((name, tensor, sp, c))
        cls_l.sort(key=lambda x: -x[2])
        box_l.sort(key=lambda x: -x[2])
        kps_l.sort(key=lambda x: -x[2])
        return cls_l, box_l, kps_l

    def __call__(self, outputs):
        cls_l, box_l, kps_l = self._classify_layers(outputs)
        if not box_l or not cls_l:
            return []
        num_anc = max(cls_l[0][3], box_l[0][3] // 4)
        anchors = self._gen_anchors(num_anc)
        all_cls = np.concatenate([t.reshape(-1, 1) for _, t, _, _ in cls_l]).flatten()
        all_box = np.concatenate([t.reshape(-1, 4) for _, t, _, _ in box_l])
        all_kps = np.concatenate([t.reshape(-1, 10) for _, t, _, _ in kps_l]) if kps_l else None
        if all_cls.min() < 0 or all_cls.max() > 1.5:
            all_cls = 1.0 / (1.0 + np.exp(-all_cls))
        n = min(all_box.shape[0], anchors.shape[0])
        anc = anchors[:n]; all_box = all_box[:n]; all_cls = all_cls[:n]
        if all_kps is not None: all_kps = all_kps[:n]
        boxes = self._decode_boxes(all_box, anc)
        kps = self._decode_kps(all_kps, anc) if all_kps is not None else None
        mask = all_cls >= self.score_thresh
        boxes, scores = boxes[mask], all_cls[mask]
        kps_f = kps[mask] if kps is not None else None
        if len(boxes) == 0: return []
        keep = self._nms(boxes, scores)
        ow, oh = self.output_w, self.output_h
        results = []
        for i in keep:
            x1 = int(np.clip(boxes[i, 0], 0, 1) * ow)
            y1 = int(np.clip(boxes[i, 1], 0, 1) * oh)
            x2 = int(np.clip(boxes[i, 2], 0, 1) * ow)
            y2 = int(np.clip(boxes[i, 3], 0, 1) * oh)
            lm = None
            if kps_f is not None:
                raw_lm = kps_f[i].reshape(5, 2)
                lm = np.zeros((5, 2), dtype=np.float32)
                lm[:, 0] = np.clip(raw_lm[:, 0], 0, 1) * ow
                lm[:, 1] = np.clip(raw_lm[:, 1], 0, 1) * oh
            results.append({"bbox": (y1, x2, y2, x1), "score": float(scores[i]), "landmarks": lm})
        return results


# arcface reference landmarks
ARCFACE_REF = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)

def align_face(image_rgb, landmarks):
    M, _ = cv2.estimateAffinePartial2D(
        landmarks.astype(np.float32), ARCFACE_REF, method=cv2.LMEDS)
    if M is None:
        cx, cy = landmarks.mean(axis=0).astype(int)
        s = 60
        crop = image_rgb[max(0, cy-s):cy+s, max(0, cx-s):cx+s]
        if crop.size == 0: return np.zeros((112, 112, 3), np.uint8)
        return cv2.resize(crop, (112, 112))
    return cv2.warpAffine(image_rgb, M, (112, 112),
                          borderMode=cv2.BORDER_REPLICATE).astype(np.uint8)

def get_arcface_embedding(arcface_engine, aligned_face_rgb):
    if aligned_face_rgb.dtype != np.uint8:
        aligned_face_rgb = np.clip(aligned_face_rgb, 0, 255).astype(np.uint8)
    out = arcface_engine.infer(aligned_face_rgb)
    emb = list(out.values())[0].flatten()
    norm = np.linalg.norm(emb)
    if norm > 0: emb /= norm
    return emb


def load_embeddings(key=None):
    # try encrypted first, fall back to plain pickle
    files = {"aigen": "aigen_arcface.pickle", "camcap": "camcap_arcface.pickle",
             "realimages": "realimages_arcface.pickle"}
    all_emb, all_cat = [], []
    for cat, fname in files.items():
        enc_path = os.path.join(ENCODINGS_DIR, fname + ".enc")
        plain_path = os.path.join(ENCODINGS_DIR, fname)

        data = None
        if os.path.exists(enc_path) and key is not None:
            try:
                from crypto_utils import decrypt_bytes
                with open(enc_path, "rb") as f:
                    raw = f.read()
                dec = decrypt_bytes(raw, key)
                data = pickle.loads(dec)
                del raw, dec
            except Exception as e:
                print(f"[ERROR] Decrypt {enc_path}: {e}")
                continue
        elif os.path.exists(plain_path):
            try:
                with open(plain_path, "rb") as f:
                    data = pickle.load(f)
            except Exception as e:
                print(f"[ERROR] {plain_path}: {e}")
                continue
        else:
            continue

        encs, names = data["encodings"], data["names"]
        if encs:
            all_emb.extend(encs); all_cat.extend(names)
            print(f"[INFO] Loaded {len(encs)} embeddings for '{cat}' (dim={len(encs[0])})")

    if not all_emb:
        print("[WARNING] No enrolled embeddings found.")
        return np.array([]), []
    emb = np.array(all_emb, dtype=np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True); norms[norms == 0] = 1
    emb /= norms
    print(f"[INFO] Total enrolled: {len(all_emb)}, dim={emb.shape[1]}")
    return emb, all_cat


def recognize_face(embedding, enrolled_emb, enrolled_cat, threshold=0.45):
    if len(enrolled_emb) == 0: return "Guest", (0, 0, 255)
    if embedding.shape[0] != enrolled_emb.shape[1]: return "Guest", (0, 0, 255)
    norm = np.linalg.norm(embedding)
    if norm > 0: embedding = embedding / norm
    sims = enrolled_emb @ embedding
    best = np.argmax(sims)
    if sims[best] >= threshold:
        cat = enrolled_cat[best]
        if cat == "camcap": return "Identified", (0, 255, 0)       # green
        elif cat in ("aigen", "realimages"): return "Guest", (255, 0, 0)  # blue
    return "Guest", (0, 0, 255)  # red


class CentroidTracker:
    def __init__(self, max_gone=12, max_dist=100,
                 reid_memory_size=50, reid_threshold=0.55):
        self.nxt = 0
        self.objs = OrderedDict()
        self.boxes = OrderedDict()
        self.gone = OrderedDict()
        self.lbls = OrderedDict()
        self.cols = OrderedDict()
        self.embs = OrderedDict()
        self.mg = max_gone
        self.md = max_dist
        self.reid_memory = OrderedDict()
        self.reid_max = reid_memory_size
        self.reid_thresh = reid_threshold

    def _c(self, b):
        t, r, bo, l = b
        return np.array([(l + r) / 2, (t + bo) / 2])

    def _reg(self, b, l, c, emb=None):
        # try re-id from memory
        if emb is not None and len(self.reid_memory) > 0:
            best_id, best_sim = None, -1
            for old_id, (old_emb, old_lbl, old_col) in self.reid_memory.items():
                sim = float(np.dot(emb, old_emb))
                if sim > best_sim:
                    best_sim, best_id = sim, old_id
            if best_sim >= self.reid_thresh and best_id is not None:
                _, old_lbl, old_col = self.reid_memory.pop(best_id)
                oid = self.nxt; self.nxt += 1
                self.objs[oid] = self._c(b); self.boxes[oid] = b
                self.gone[oid] = 0; self.lbls[oid] = old_lbl
                self.cols[oid] = old_col; self.embs[oid] = emb
                return

        oid = self.nxt; self.nxt += 1
        self.objs[oid] = self._c(b); self.boxes[oid] = b
        self.gone[oid] = 0
        self.lbls[oid] = l if l is not None else "Guest"
        self.cols[oid] = c if c is not None else (0, 0, 255)
        if emb is not None: self.embs[oid] = emb

    def _dereg(self, i):
        # save embedding to re-id memory
        if i in self.embs:
            self.reid_memory[i] = (self.embs[i], self.lbls.get(i, "Guest"),
                                   self.cols.get(i, (0, 0, 255)))
            while len(self.reid_memory) > self.reid_max:
                self.reid_memory.popitem(last=False)
        for d in (self.objs, self.boxes, self.gone, self.lbls, self.cols, self.embs):
            d.pop(i, None)

    def update(self, dets, lbls, cols, embeddings=None):
        if not dets:
            for i in list(self.gone):
                self.gone[i] += 1
                if self.gone[i] > self.mg: self._dereg(i)
            return [(i, self.boxes[i], self.lbls[i], self.cols[i]) for i in self.objs]

        emb_list = embeddings or [None] * len(dets)
        if not self.objs:
            for b, l, c, e in zip(dets, lbls, cols, emb_list):
                self._reg(b, l, c, e)
        else:
            ids = list(self.objs.keys())
            oc = np.array([self.objs[i] for i in ids])
            ic = np.array([self._c(b) for b in dets])
            D = np.linalg.norm(oc[:, None] - ic[None], axis=2)
            rows = D.min(1).argsort()
            cols_idx = D.argmin(1)[rows]
            ur, uc = set(), set()
            for r, ci in zip(rows, cols_idx):
                if r in ur or ci in uc or D[r, ci] > self.md: continue
                oid = ids[r]
                self.objs[oid] = ic[ci]; self.boxes[oid] = dets[ci]
                if lbls[ci] is not None: self.lbls[oid] = lbls[ci]
                if cols[ci] is not None: self.cols[oid] = cols[ci]
                if emb_list[ci] is not None: self.embs[oid] = emb_list[ci]
                self.gone[oid] = 0; ur.add(r); uc.add(ci)
            for r in set(range(len(ids))) - ur:
                self.gone[ids[r]] += 1
                if self.gone[ids[r]] > self.mg: self._dereg(ids[r])
            for ci in set(range(len(dets))) - uc:
                self._reg(dets[ci], lbls[ci], cols[ci], emb_list[ci])

        return [(i, self.boxes[i], self.lbls[i], self.cols[i]) for i in self.objs]

# Use GaussianBlur 
def blur_face(frame, top, right, bottom, left):
    t, b = max(0, top), min(frame.shape[0], bottom)
    l, r = max(0, left), min(frame.shape[1], right)
    if b <= t or r <= l: return
    roi = frame[t:b, l:r]
    kh = max(9, (b - t) // 3) * 2 + 1
    kw = max(9, (r - l) // 3) * 2 + 1
    frame[t:b, l:r] = cv2.GaussianBlur(roi, (kw, kh), 0)

# Use Pixelation Blur
# def blur_face(frame, top, right, bottom, left):
#     t, b = max(0, top), min(frame.shape[0], bottom)
#     l, r = max(0, left), min(frame.shape[1], right)
#     if b <= t or r <= l: return
#     roi = frame[t:b, l:r]
#     small = cv2.resize(roi, (8, 8), interpolation=cv2.INTER_LINEAR)
#     frame[t:b, l:r] = cv2.resize(small, (r - l, b - t), interpolation=cv2.INTER_NEAREST)

def draw_box(frame, top, right, bottom, left, label, color):
    cv2.rectangle(frame, (left, top), (right, bottom), color, 3)
    cv2.rectangle(frame, (left - 3, top - 35), (right + 3, top), color, cv2.FILLED)
    cv2.putText(frame, label, (left + 6, top - 6),
                cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)

def draw_hud(frame, fps, recording=True):
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs, thick, margin = 0.6, 1, 10
    red = (0, 0, 255)

    fps_text = f"FPS: {fps:.1f}"
    (tw, th), _ = cv2.getTextSize(fps_text, font, fs, thick)
    fps_y = margin + th
    cv2.putText(frame, fps_text, (w - tw - margin, fps_y),
                font, fs, red, thick, cv2.LINE_AA)

    quit_text = "Q: Quit"
    (tw2, th2), _ = cv2.getTextSize(quit_text, font, fs, thick)
    cv2.putText(frame, quit_text, (w - tw2 - margin, fps_y + th2 + 5),
                font, fs, red, thick, cv2.LINE_AA)

    if recording:
        cv2.circle(frame, (margin + 8, margin + 8), 6, red, -1)
        cv2.putText(frame, "REC", (margin + 20, margin + 13),
                    font, 0.5, red, 1, cv2.LINE_AA)
