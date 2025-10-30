#!/usr/bin/env python3
"""Compute correct output window for ground plane test."""

import sys
import numpy as np
sys.path.insert(0, '/home/markus/src/gstreamer/src')
from pylib.homography import Homography2

h = Homography2()
h.cam_width = 720
h.cam_height = 720

# Camera above ground, tilted down
h.camera_x = 0.0
h.camera_y = 0.0
h.camera_z = 12000.0  # 12m above ground
h.roll = 180.0
h.pitch = -60.0
h.yaw = 0.0

# Ground plane
h.plane_normal = [0.0, 0.0, 1.0]
h.plane_distance = 1.0

print("=== Computing Ground Plane Output Window ===\n")

# Camera position
C = np.array([[h.camera_x], [h.camera_y], [h.camera_z]], dtype=np.float32)
print(f"Camera position C: {C.T}")

# Optical axis
R = h.R
optical_axis = R.T @ np.array([[0], [0], [1]], dtype=np.float32)
print(f"Optical axis: {optical_axis.T}")

# Find where optical axis intersects ground plane
# Ray: P(t) = C + t * optical_axis
# Plane: n^T · P = d
# Solve: n^T · (C + t * optical_axis) = d
# t = (d - n^T · C) / (n^T · optical_axis)

n = h.plane_normal
d = h.plane_distance

n_dot_C = float((n.T @ C)[0, 0])
n_dot_dir = float((n.T @ optical_axis)[0, 0])

print(f"\nn^T · C = {n_dot_C:.1f}")
print(f"n^T · optical_axis = {n_dot_dir:.4f}")

if abs(n_dot_dir) > 1e-6:
    t = (d - n_dot_C) / n_dot_dir
    intersection = C + t * optical_axis
    print(f"\nIntersection parameter t = {t:.1f}mm")
    print(f"Optical axis intersects ground at: {intersection.T}")
    print(f"This is {t/1000:.1f} meters along the optical axis")

    # This intersection point is where we should center our output window
    center_x = float(intersection[0, 0])
    center_y = float(intersection[1, 0])

    print(f"\nSuggested output window center: ({center_x:.1f}, {center_y:.1f}) mm")
    print(f"That's ({center_x/1000:.2f}, {center_y/1000:.2f}) meters")

    # For a 5m × 5m window
    out_scale = 5000.0
    out_origin_x = center_x - 0.5 * out_scale
    out_origin_y = center_y - 0.5 * out_scale

    print(f"\nFor 5m × 5m window:")
    print(f"out_origin_x_mm = {out_origin_x:.1f}")
    print(f"out_origin_y_mm = {out_origin_y:.1f}")

    # Test this configuration
    h.out_scale_x_mm_per_uv = out_scale
    h.out_scale_y_mm_per_uv = out_scale
    h.out_origin_x_mm = out_origin_x
    h.out_origin_y_mm = out_origin_y
    h.y_up_src = True

    M = h.normalized
    print(f"\nWith this window, testing center mapping:")
    center_in = np.array([[0.5], [0.5], [1.0]])
    center_out_h = M @ center_in
    if abs(center_out_h[2, 0]) > 1e-6:
        center_out = center_out_h[:2, 0] / center_out_h[2, 0]
        print(f"Center (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")
    else:
        print("Singularity!")

else:
    print("\nOptical axis is parallel to ground plane - no intersection!")
