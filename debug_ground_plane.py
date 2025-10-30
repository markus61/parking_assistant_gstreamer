#!/usr/bin/env python3
"""Debug script for ground plane test."""

import sys
import numpy as np
sys.path.insert(0, '/home/markus/src/gstreamer/src')
from pylib.homography import Homography2

# Create Homography2 instance with same setup as ground plane test
h = Homography2()
h.cam_width = 720
h.cam_height = 720

# Try roll=180 + pitch=-60 for oblique view downward
h.camera_x = 0.0
h.camera_y = 0.0
h.camera_z = 12000.0  # 12m above ground
h.roll = 180.0  # Flip to look down
h.pitch = -60.0  # Then tilt for oblique angle
h.yaw = 0.0

# Plane: horizontal ground at Z=1mm
h.plane_normal = [0.0, 0.0, 1.0]
h.plane_distance = 1.0

# Output window: span 5m x 5m
h.out_scale_x_mm_per_uv = 5000.0
h.out_scale_y_mm_per_uv = 5000.0
h.out_origin_x_mm = -2500.0
h.out_origin_y_mm = -2500.0
h.y_up_src = True

print("=== Ground Plane Debug ===")
print(f"Camera position: ({h.camera_x}, {h.camera_y}, {h.camera_z})")
print(f"Pitch: {h.pitch}°")
print(f"\nR matrix (rotation):\n{h.R}")

# Check what direction the camera is looking
# The optical axis in camera coords is [0, 0, 1] (along +Z)
# After rotation R^T, it becomes the world direction
optical_axis_world = h.R.T @ np.array([[0], [0], [1]], dtype=np.float32)
print(f"\nOptical axis in world coords: {optical_axis_world.T}")

# Check if the camera can see the ground plane
C = np.array([[h.camera_x], [h.camera_y], [h.camera_z]], dtype=np.float32)
n = h.plane_normal
d = h.plane_distance
distance_to_plane = float((n.T @ C)[0, 0] - d)
print(f"\nDistance from camera to plane: {distance_to_plane:.1f}mm")

# Get H matrix
print(f"\nH matrix:\n{h.H}")

# Get normalized matrix
M = h.normalized
print(f"\nNormalized matrix M:\n{M}")

# Test center point
center_in = np.array([[0.5], [0.5], [1.0]])
center_out_h = M @ center_in
center_out = center_out_h[:2, 0] / center_out_h[2, 0]
print(f"\nCenter (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")

# Test corners
print("\nCorner mappings:")
for label, (x, y) in [("TL", (0, 0)), ("TR", (1, 0)), ("BR", (1, 1)), ("BL", (0, 1))]:
    pt_in = np.array([[x], [y], [1.0]])
    pt_out_h = M @ pt_in
    w = pt_out_h[2, 0]
    if abs(w) > 1e-6:
        pt_out = pt_out_h[:2, 0] / w
        print(f"  {label} ({x},{y}) -> ({pt_out[0]:.4f}, {pt_out[1]:.4f})")
    else:
        print(f"  {label} ({x},{y}) -> (inf/undefined, w≈0)")
