"""
Camera configuration and homography computation for perspective correction.

This module handles camera calibration parameters and computes the homography
transformation matrices needed for perspective correction in the GStreamer pipeline.
"""

import math
from typing import Tuple


class CameraConfig:
    """
    Camera configuration for dual Radxa 4K cameras with perspective correction.

    Hardware specifications (Radxa 4K cameras):
        - Focal Length: 2.95mm ±5%
        - Horizontal FOV: 75° ±3%
        - Vertical FOV: 59° ±2%
        - Resolution: 1280x720 pixels

    Physical installation:
        - Cameras mounted horizontally at 0.9m height
        - Each camera rotated ±90° around optical axis (roll)
        - Cameras point outward by ±37.5° (pan angle = FOV/2)
        - No vertical tilt (pointing horizontally at walls)
        - Camera spacing configurable (0.1m or 1.5m)

    Usage:
        config = CameraConfig()
        left_h = config.compute_homography_matrix('left')
        right_h = config.compute_homography_matrix('right')
    """

    def __init__(
        self,
        h_fov: float = 75.0,
        v_fov: float = 59.0,
        focal_length_mm: float = 2.95,
        resolution: Tuple[int, int] = (1280, 720),
        camera_height: float = 0.9,
        tilt_angle: float = 0.0,
        pan_angle: float = 37.5,
        camera_spacing: float = 0.1,
        distance_to_wall: float = 4.0,
        reference_object_size: float = 0.094
    ):
        """
        Initialize camera configuration.

        Args:
            h_fov: Horizontal field of view in degrees (default: 75.0)
            v_fov: Vertical field of view in degrees (default: 59.0)
            focal_length_mm: Camera focal length in mm (default: 2.95)
            resolution: Image resolution (width, height) in pixels (default: 1280x720)
            camera_height: Height from ground in meters (default: 0.9)
            tilt_angle: Vertical tilt in degrees, 0=horizontal (default: 0.0)
            pan_angle: Horizontal pan outward in degrees (default: 37.5)
            camera_spacing: Distance between cameras in meters (default: 0.1)
            distance_to_wall: Distance to target wall in meters (default: 4.0)
            reference_object_size: Known object size for calibration in meters (default: 0.094)
        """
        # Hardware intrinsics (fixed)
        self.h_fov: float = h_fov
        self.v_fov: float = v_fov
        self.focal_length_mm: float = focal_length_mm
        self.resolution: Tuple[int, int] = resolution

        # Physical installation (configurable)
        self.camera_height: float = camera_height
        self.tilt_angle: float = tilt_angle
        self.pan_angle: float = pan_angle
        self.camera_spacing: float = camera_spacing

        # Scene parameters (configurable)
        self.distance_to_wall: float = distance_to_wall

        # Calibration reference
        self.reference_object_size: float = reference_object_size

    def compute_focal_length_pixels(self) -> Tuple[float, float]:
        """
        Compute focal length in pixels from FOV and resolution.

        Returns:
            Tuple of (fx, fy) focal lengths in pixels
        """
        width, height = self.resolution

        # fx = (width / 2) / tan(h_fov / 2)
        fx = (width / 2.0) / math.tan(math.radians(self.h_fov / 2.0))

        # fy = (height / 2) / tan(v_fov / 2)
        fy = (height / 2.0) / math.tan(math.radians(self.v_fov / 2.0))

        return (fx, fy)

    def compute_principal_point(self) -> Tuple[float, float]:
        """
        Compute principal point (optical center) in pixels.
        Typically at image center unless there's optical offset.

        Returns:
            Tuple of (cx, cy) principal point coordinates in pixels
        """
        width, height = self.resolution
        cx = width / 2.0
        cy = height / 2.0
        return (cx, cy)

    def compute_homography_matrix(self, camera_side: str) -> list:
        """
        Compute 3x3 homography matrix for perspective correction.

        Corrects the keystone distortion caused by camera pan angle.
        The homography transforms the trapezoidal view from an angled camera
        into a rectangular orthographic projection.

        Args:
            camera_side: 'left' or 'right' to determine pan direction

        Returns:
            List of 9 floats in row-major order [h11, h12, h13, h21, h22, h23, h31, h32, h33]

        Raises:
            ValueError: If camera_side is not 'left' or 'right'
        """
        if camera_side not in ['left', 'right']:
            raise ValueError(f"camera_side must be 'left' or 'right', got '{camera_side}'")

        # Determine pan direction: left camera pans left (negative), right pans right (positive)
        pan_sign = -1 if camera_side == 'left' else 1
        pan_radians = math.radians(pan_sign * self.pan_angle)

        # Get camera intrinsic parameters
        fx, fy = self.compute_focal_length_pixels()
        cx, cy = self.compute_principal_point()

        # Compute rotation matrix for pan angle (rotation around Y-axis in world coords)
        # After 90° roll, this becomes rotation in the camera's effective coordinate system
        cos_p = math.cos(pan_radians)
        sin_p = math.sin(pan_radians)

        # Build homography H = K * R_pan * K^-1 using manual matrix operations
        # This avoids numpy dependency

        # K = [[fx, 0, cx],
        #      [0, fy, cy],
        #      [0,  0,  1]]

        # K_inv = [[1/fx,    0, -cx/fx],
        #          [   0, 1/fy, -cy/fy],
        #          [   0,    0,      1]]

        # R_pan = [[cos_p, 0, sin_p],
        #          [    0, 1,     0],
        #          [-sin_p, 0, cos_p]]

        # Compute H = K * R_pan * K_inv step by step

        # Step 1: R_pan * K_inv
        # Result is 3x3 matrix
        r_kinv = [
            [cos_p / fx, 0.0, -cos_p * cx / fx + sin_p],
            [0.0, 1.0 / fy, -cy / fy],
            [-sin_p / fx, 0.0, sin_p * cx / fx + cos_p]
        ]

        # Step 2: K * (R_pan * K_inv)
        # H[i][j] = sum over k: K[i][k] * r_kinv[k][j]
        h11 = fx * r_kinv[0][0]  # fx * (cos_p / fx)
        h12 = fx * r_kinv[0][1]  # fx * 0
        h13 = fx * r_kinv[0][2] + cx * r_kinv[2][2]  # fx * (...) + cx * (...)

        h21 = fy * r_kinv[1][0]  # fy * 0
        h22 = fy * r_kinv[1][1]  # fy * (1/fy)
        h23 = fy * r_kinv[1][2] + cy * r_kinv[2][2]  # fy * (...) + cy * (...)

        h31 = r_kinv[2][0]
        h32 = r_kinv[2][1]
        h33 = r_kinv[2][2]

        # Normalize so h33 = 1.0
        H = [
            h11 / h33, h12 / h33, h13 / h33,
            h21 / h33, h22 / h33, h23 / h33,
            h31 / h33, h32 / h33, 1.0
        ]

        return H

    def compute_pixels_per_meter(self, elephant_height_pixels: float) -> float:
        """
        Compute pixel-to-meter conversion ratio using reference object.

        Args:
            elephant_height_pixels: Measured height of elephant in corrected image

        Returns:
            Pixels per meter ratio
        """
        return elephant_height_pixels / self.reference_object_size

    def __repr__(self) -> str:
        """String representation of camera configuration."""
        return (
            f"CameraConfig(h_fov={self.h_fov}°, v_fov={self.v_fov}°, "
            f"resolution={self.resolution}, "
            f"pan_angle={self.pan_angle}°, spacing={self.camera_spacing}m, "
            f"distance={self.distance_to_wall}m)"
        )
