#!/usr/bin/env python3

import os
import sys
import pickle
import hashlib

import cv2
import numpy as np

from hailo_utils import (
    SCRIPT_DIR, MODELS_DIR, ENCODINGS_DIR, FACEDATA_DIR,
    SCRFD_HEF, ARCFACE_HEF, SCRFD_INPUT_SIZE,
    HailoEngine, SCRFDPostProcessor, align_face, get_arcface_embedding
)
from crypto_utils import (
    get_session_key, decrypt_file, encrypt_data_to_file,
    encrypt_unprotected_images, IMAGE_EXTS
)

CATEGORIES = ["aigen", "camcap", "realimages"]


def _list_image_files(folder_path):
    if not os.path.isdir(folder_path):
        return []
    files = []
    for fname in sorted(os.listdir(folder_path)):
        if fname.endswith(".enc"):
            files.append(fname)
        elif fname.lower().endswith(IMAGE_EXTS):
            files.append(fname)
    return files


def _compute_folder_hash(folder_path):
    # hash from sorted filenames + sizes + mtimes
    files = _list_image_files(folder_path)
    if not files:
        return None
    entries = []
    for fname in files:
        fpath = os.path.join(folder_path, fname)
        stat = os.stat(fpath)
        entries.append(f"{fname}:{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.md5("|".join(entries).encode()).hexdigest()


def _read_stored_hash(hash_path):
    if not os.path.exists(hash_path):
        return None
    try:
        with open(hash_path, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def _write_stored_hash(hash_path, hash_value):
    try:
        with open(hash_path, "w") as f:
            f.write(hash_value)
    except Exception as e:
        print(f"[WARNING] Could not write hash file: {e}")


def _pickle_exists(cat):
    enc_path = os.path.join(ENCODINGS_DIR, f"{cat}_arcface.pickle.enc")
    plain_path = os.path.join(ENCODINGS_DIR, f"{cat}_arcface.pickle")
    return os.path.exists(enc_path) or os.path.exists(plain_path)


def _needs_enrollment(cat):
    cat_dir = os.path.join(FACEDATA_DIR, cat)

    if not os.path.isdir(cat_dir):
        return False
    images = _list_image_files(cat_dir)
    if not images:
        return False

    # aigen/ realimages - onetime
    if cat in ("aigen", "realimages"):
        if _pickle_exists(cat):
            return False
        return True

    # camcap reenroll when images change
    if not _pickle_exists(cat):
        return True

    hash_path = os.path.join(ENCODINGS_DIR, f"{cat}.hash")
    current_hash = _compute_folder_hash(cat_dir)
    stored_hash = _read_stored_hash(hash_path)

    if current_hash == stored_hash:
        return False
    return True


def _load_image(path, fname, key):
    if fname.endswith(".enc"):
        try:
            dec_bytes = decrypt_file(path, key)
            nparr = np.frombuffer(dec_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            del dec_bytes, nparr
            return img
        except Exception as e:
            print(f"  [SKIP] Decrypt failed: {fname}: {e}")
            return None
    else:
        return cv2.imread(path)


def _enroll_category(cat, scrfd, arcface, key):
    cat_dir = os.path.join(FACEDATA_DIR, cat)
    out_path = os.path.join(ENCODINGS_DIR, f"{cat}_arcface.pickle.enc")

    imgs = _list_image_files(cat_dir)
    if not imgs:
        return False

    print(f"\n[INFO] Enrolling '{cat}' ({len(imgs)} images)...")
    encodings = []
    names = []

    for i, fname in enumerate(imgs):
        path = os.path.join(cat_dir, fname)

        img = _load_image(path, fname, key)
        if img is None:
            print(f"  [SKIP] Cannot read: {fname}")
            continue

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        post = SCRFDPostProcessor(
            SCRFD_INPUT_SIZE, score_thresh=0.5, nms_thresh=0.4,
            output_w=w, output_h=h)
        inp = cv2.resize(rgb, (SCRFD_INPUT_SIZE, SCRFD_INPUT_SIZE))
        dets = post(scrfd.infer(inp.astype(np.float32)))

        if not dets:
            del img, rgb, inp
            print(f"  [SKIP] No face found: {fname}")
            continue

        best = max(dets, key=lambda d: d["score"])
        lm = best.get("landmarks")
        if lm is None:
            del img, rgb, inp
            print(f"  [SKIP] No landmarks: {fname}")
            continue

        aligned = align_face(rgb, lm)
        emb = get_arcface_embedding(arcface, aligned)
        encodings.append(emb)
        names.append(cat)

        del img, rgb, inp, aligned

        if (i + 1) % 10 == 0 or i == len(imgs) - 1:
            print(f"  [{i+1}/{len(imgs)}] {len(encodings)} faces enrolled")

    if not encodings:
        print(f"[WARNING] No valid faces for '{cat}'.")
        return False

    # encrypt pickle
    pkl_bytes = pickle.dumps({"encodings": encodings, "names": names})
    encrypt_data_to_file(pkl_bytes, out_path, key)
    del pkl_bytes
    print(f"[INFO] Saved {len(encodings)} embeddings (encrypted) -> {out_path}")

    # remove old unencrypted pickle
    old_plain = os.path.join(ENCODINGS_DIR, f"{cat}_arcface.pickle")
    if os.path.exists(old_plain):
        os.remove(old_plain)
        print(f"[INFO] Removed old unencrypted pickle: {os.path.basename(old_plain)}")

    # store hash for camcap change detection
    if cat == "camcap":
        hash_val = _compute_folder_hash(cat_dir)
        if hash_val:
            hash_path = os.path.join(ENCODINGS_DIR, f"{cat}.hash")
            _write_stored_hash(hash_path, hash_val)

    return True


def enroll_if_needed(key=None):
    if key is None:
        key = get_session_key()

    os.makedirs(ENCODINGS_DIR, exist_ok=True)

    # encrypt any manually added plain images in camcap
    camcap_dir = os.path.join(FACEDATA_DIR, "camcap")
    encrypt_unprotected_images(camcap_dir, key)

    cats_needed = [cat for cat in CATEGORIES if _needs_enrollment(cat)]

    if not cats_needed:
        print("[INFO] All enrollments up to date. Skipping.")
        return

    print(f"[INFO] Enrollment needed for: {', '.join(cats_needed)}")
    print("[INFO] Loading SCRFD face detection on Hailo...")
    scrfd = HailoEngine(SCRFD_HEF)
    print("[INFO] Loading ArcFace embedding on Hailo...")
    arcface = HailoEngine(ARCFACE_HEF)

    for cat in cats_needed:
        _enroll_category(cat, scrfd, arcface, key)

    print("[INFO] Auto-enrollment complete.")


def main():
    key = get_session_key()
    enroll_if_needed(key)


if __name__ == "__main__":
    main()
