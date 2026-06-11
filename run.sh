#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export DISPLAY="${DISPLAY:-:0}"
source "$DIR/hailo-rpi5-examples-25.7.0/venv_hailo_rpi_examples/bin/activate"
python3 launcher.py