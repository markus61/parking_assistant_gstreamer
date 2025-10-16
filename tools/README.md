# Camera Calibration Tools

This directory contains tools for calibrating the dual camera system.

## calibrate_cameras.py

Camera calibration tool for perspective correction and pixel-to-meter scaling.

### Requirements

```bash
pip install opencv-python numpy
```

### Usage

See the main [CALIBRATION.md](../../CALIBRATION.md) guide for detailed instructions.

**Quick start:**

```bash
# Manual calibration (click 4 corners)
python src/tools/calibrate_cameras.py \
    --left left_calibration.jpg \
    --right right_calibration.jpg \
    --pattern manual \
    --width 1.5 \
    --height 1.0

# Automatic checkerboard detection
python src/tools/calibrate_cameras.py \
    --left left_calibration.jpg \
    --right right_calibration.jpg \
    --pattern checkerboard \
    --rows 7 \
    --cols 9 \
    --width 0.9 \
    --height 0.7
```

### Output

Saves calibration to `config/camera_calibration.json` containing:
- Left and right camera homography matrices
- Pixel-to-meter scale factor

This file is automatically loaded by the GStreamer pipeline on startup.
