#!/usr/bin/env python3
"""Validate all three test configurations without opening GUI windows."""

import sys
import numpy as np
sys.path.insert(0, '/home/markus/src/gstreamer/src')
from pylib.homography import Homography2

def validate_test(name, h):
    """Validate a Homography2 configuration."""
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"{'='*60}")

    # Print setup
    print(f"Camera: position=({h.camera_x}, {h.camera_y}, {h.camera_z})mm")
    print(f"Camera: roll={h.roll}°, pitch={h.pitch}°, yaw={h.yaw}°")
    print(f"Plane: normal={h.plane_normal.T}, distance={h.plane_distance}mm")

    # Calculate optical axis
    R = h.R
    optical_axis = R.T @ np.array([[0], [0], [1]], dtype=np.float32)
    print(f"Optical axis: {optical_axis.T}")

    # Check distance to plane
    C = np.array([[h.camera_x], [h.camera_y], [h.camera_z]], dtype=np.float32)
    n = h.plane_normal
    d = h.plane_distance
    dist_to_plane = float((n.T @ C)[0, 0] - d)
    print(f"Distance camera→plane: {dist_to_plane:.1f}mm")

    # Get normalized matrix
    try:
        M = h.normalized
        print(f"\nMatrix M computed successfully")
        print(f"M[0,:] = {M[0,:]}")
        print(f"M[1,:] = {M[1,:]}")
        print(f"M[2,:] = {M[2,:]}")

        # Test center mapping
        center_in = np.array([[0.5], [0.5], [1.0]])
        center_out_h = M @ center_in
        w = center_out_h[2, 0]
        if abs(w) > 1e-6:
            center_out = center_out_h[:2, 0] / w
            print(f"\nCenter (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")

            # Check if close to (0.5, 0.5)
            error = np.abs(center_out - 0.5)
            if np.max(error) < 0.02:
                print(f"✓ CENTER MAPPING CORRECT (error < 0.02)")
            else:
                print(f"✗ CENTER MAPPING INCORRECT (error = {error})")
        else:
            print(f"✗ SINGULARITY: w ≈ 0")

    except Exception as e:
        print(f"✗ ERROR computing normalized matrix: {e}")

# Test 1: Fronto-parallel identity
print("="*60)
print("VALIDATING ALL THREE TESTS")
print("="*60)

h1 = Homography2()
h1.cam_width = 720
h1.cam_height = 720
h1.camera_x = 0.0
h1.camera_y = 0.0
h1.camera_z = 0.0
h1.roll = 0.0
h1.pitch = 0.0
h1.yaw = 0.0
h1.plane_normal = [0.0, 0.0, 1.0]
h1.plane_distance = 4000.0
fx = h1.K[0, 0]
mm_per_px = h1.plane_distance / fx
out_scale = mm_per_px * h1.cam_width
h1.out_scale_x_mm_per_uv = out_scale
h1.out_scale_y_mm_per_uv = out_scale
h1.out_origin_x_mm = -0.5 * out_scale
h1.out_origin_y_mm = -0.5 * out_scale
h1.y_up_src = True

validate_test("TEST 1: Fronto-parallel Identity", h1)

# Test 2: Yaw rotation (same as test 1 initially)
h2 = Homography2()
h2.cam_width = 720
h2.cam_height = 720
h2.camera_x = 0.0
h2.camera_y = 0.0
h2.camera_z = 0.0
h2.roll = 0.0
h2.pitch = 0.0
h2.yaw = 15.0  # Test with some yaw
h2.plane_normal = [0.0, 0.0, 1.0]
h2.plane_distance = 4000.0
h2.out_scale_x_mm_per_uv = out_scale
h2.out_scale_y_mm_per_uv = out_scale
h2.out_origin_x_mm = -0.5 * out_scale
h2.out_origin_y_mm = -0.5 * out_scale
h2.y_up_src = True

validate_test("TEST 2: Yaw Rotation (yaw=15°)", h2)

# Test 3: Ground plane oblique
h3 = Homography2()
h3.cam_width = 720
h3.cam_height = 720
h3.camera_x = 0.0
h3.camera_y = 0.0
h3.camera_z = 12000.0  # 12m above ground
h3.roll = 180.0  # Look down
h3.pitch = 0.0
h3.yaw = 0.0
h3.plane_normal = [0.0, 0.0, 1.0]
h3.plane_distance = 1.0
h3.out_scale_x_mm_per_uv = 5000.0
h3.out_scale_y_mm_per_uv = 5000.0
h3.out_origin_x_mm = -2500.0
h3.out_origin_y_mm = -2500.0
h3.y_up_src = True

validate_test("TEST 3: Ground Plane Oblique (roll=180°)", h3)

print(f"\n{'='*60}")
print("VALIDATION COMPLETE")
print(f"{'='*60}\n")
