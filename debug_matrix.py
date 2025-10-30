#!/usr/bin/env python3
"""Debug script to check Homography2 matrix values for frontoparallel test."""

import sys
import numpy as np
sys.path.insert(0, '/home/markus/src/gstreamer/src')
from pylib.homography import Homography2

# Create Homography2 instance with same setup as frontoparallel test
h = Homography2()
h.cam_width = 720
h.cam_height = 720

# Camera setup: at origin, looking at wall 4m away
# With +X forward, +Y right, +Z up: camera at origin looks along +X axis
h.camera_x = 0.0
h.camera_y = 0.0
h.camera_z = 0.0  # At origin (not elevated)
h.roll = 0.0
h.pitch = 0.0
h.yaw = 0.0

# Plane: vertical wall perpendicular to camera's optical axis (+Z)
h.plane_normal = [0.0, 0.0, 1.0]  # Wall perpendicular to Z-axis
h.plane_distance = 4000.0  # Wall at Z=4000mm

# Output window: calculate scaling to span central field
fx = h.K[0, 0]  # Focal length in pixels
mm_per_px = h.plane_distance / fx
out_scale = mm_per_px * h.cam_width

h.out_scale_x_mm_per_uv = out_scale
h.out_scale_y_mm_per_uv = out_scale
h.out_origin_x_mm = -0.5 * out_scale  # Center the window
h.out_origin_y_mm = -0.5 * out_scale
h.y_up_src = True  # GL UV convention (bottom-left origin)

print("=== Homography2 Debug ===")
print(f"K matrix:\n{h.K}")
print(f"\nR matrix:\n{h.R}")
print(f"\nCamera position: ({h.camera_x}, {h.camera_y}, {h.camera_z})")

# Manually calculate t
C = np.array([[h.camera_x], [h.camera_y], [h.camera_z]], dtype=np.float32)
t_manual = -h.R @ C
print(f"\nCamera center C: {C.T}")
print(f"Translation t = -R·C: {t_manual.T}")

print(f"\nPlane normal n: {h.plane_normal.T}")
print(f"Plane distance d: {h.plane_distance}")
print(f"\nPlane basis B:\n{h._plane_basis}")

# Manually calculate H
n = h.plane_normal
d = h.plane_distance
B = h._plane_basis
K = h.K
R = h.R

# H = K·(R - t·n^T/d)·B
t_n_T = t_manual @ n.T  # 3x1 @ 1x3 = 3x3
t_n_T_over_d = t_n_T / d
R_minus_t_n_T_over_d = R - t_n_T_over_d
H_manual = K @ R_minus_t_n_T_over_d @ B

print(f"\nt @ n^T:\n{t_n_T}")
print(f"\n(t @ n^T) / d:\n{t_n_T_over_d}")
print(f"\nR - (t @ n^T)/d:\n{R_minus_t_n_T_over_d}")
print(f"\nH_manual = K·(R - t·n^T/d)·B:\n{H_manual}")
print(f"\nH from property:\n{h.H}")

print(f"\n=== Normalized Matrix Breakdown ===")

# Manually calculate normalized matrix
W = h.cam_width
H_img = h.cam_height
N_src_inv = np.array([
    [1.0 / W,        0.0,     0.0],
    [    0.0, -1.0 / H_img, H_img],
    [    0.0,        0.0,     1.0]
], dtype=np.float32)

Sx = h.out_scale_x_mm_per_uv
Sy = h.out_scale_y_mm_per_uv
X0 = h.out_origin_x_mm
Y0 = h.out_origin_y_mm
A = np.array([
    [Sx,  0.0, X0],
    [0.0,  Sy, Y0],
    [0.0, 0.0, 1.0]
], dtype=np.float32)

print(f"\nN_src^{{-1}} (pixels → UV):\n{N_src_inv}")
print(f"\nA (output UV → plane mm):\n{A}")
print(f"\nM = N_src^{{-1}} · H · A")

M_manual = N_src_inv @ h.H @ A
print(f"\nM manual:\n{M_manual}")
print(f"\nM from property:\n{h.normalized}")
print(f"\nM[0,:] = {h.normalized[0,:]}")
print(f"M[1,:] = {h.normalized[1,:]}")
print(f"M[2,:] = {h.normalized[2,:]}")

# Test center point mapping
center_in = np.array([[0.5], [0.5], [1.0]])
center_out_h = h.normalized @ center_in
center_out = center_out_h[:2, 0] / center_out_h[2, 0]
print(f"\nCenter (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")

# Test corners
corners = [
    (0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)
]
print("\nCorner mappings:")
for x, y in corners:
    pt_in = np.array([[x], [y], [1.0]])
    pt_out_h = h.normalized @ pt_in
    pt_out = pt_out_h[:2, 0] / pt_out_h[2, 0]
    print(f"  ({x},{y}) -> ({pt_out[0]:.4f}, {pt_out[1]:.4f})")
