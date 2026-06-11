#!/bin/bash

set -e

MODELS_DIR="$(dirname "$0")/models"
mkdir -p "$MODELS_DIR"

# hailo-10h model zoo URLs
BASE_V52="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h"
BASE_V51="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.1.0/hailo10h"
BASE_V50="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.0.0/hailo10h"

download_model() {
    local name="$1"
    local dest="$MODELS_DIR/$name"

    if [ -f "$dest" ]; then
        echo "[OK] $name already exists. Skipping."
        return 0
    fi

    for base in "$BASE_V52" "$BASE_V51" "$BASE_V50"; do
        url="$base/$name"
        echo "[INFO] Trying: $url"
        if wget -q --spider "$url" 2>/dev/null; then
            echo "[INFO] Downloading $name ..."
            wget -O "$dest" "$url"
            echo "[OK] Saved -> $dest"
            return 0
        fi
    done

    echo ""
    echo "[WARNING] Could not auto-download $name"
    echo ""
    echo "Download manually from the Hailo Model Zoo:"
    echo "  https://github.com/hailo-ai/hailo_model_zoo"
    echo ""
    echo "Navigate to: docs/public_models/HAILO10H/"
    echo "Look for the 'Compiled' (H) download link for $name"
    echo "Save the file to: $dest"
    echo ""
    return 1
}

echo " Hailo-10H Model Downloader"
echo ""

# face detection
echo "── [1/3] scrfd_2.5g.hef ──"
download_model "scrfd_2.5g.hef" || true

# face recognition
echo ""
echo "── [2/3] arcface_mobilefacenet.hef ──"
download_model "arcface_mobilefacenet.hef" || true

# pose estimation
echo ""
echo "── [3/3] yolov8s_pose.hef ──"
download_model "yolov8s_pose.hef" || true

echo ""
echo " Download complete!"
echo " Models directory: $MODELS_DIR"
ls -lh "$MODELS_DIR"/*.hef 2>/dev/null || echo " (no .hef files found)"
echo ""
