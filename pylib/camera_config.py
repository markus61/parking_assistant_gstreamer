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
        reference_object_size: float = 0.094,
        enable_perspective_correction: bool = True
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
            enable_perspective_correction: Enable/disable perspective correction (default: True)
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

        # Perspective correction control
        self.enable_perspective_correction: bool = enable_perspective_correction

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
        Compute 3x3 homography matrix for perspective correction in texture space.

        Corrects the keystone distortion caused by camera pan angle.
        Works in normalized texture coordinates [0,1], not pixel space.

        For a camera panned by angle θ viewing a frontal plane:
        - The plane appears as a trapezoid (keystone distortion)
        - One edge is compressed (far from camera), other expanded (near)
        - Homography warps this back to a rectangle

        Args:
            camera_side: 'left' or 'right' to determine pan direction

        Returns:
            List of 9 floats in row-major order [h11, h12, h13, h21, h22, h23, h31, h32, h33]
            For use directly in GL shader with normalized [0,1] texture coordinates.

        Raises:
            ValueError: If camera_side is not 'left' or 'right'
        """
        if camera_side not in ['left', 'right']:
            raise ValueError(f"camera_side must be 'left' or 'right', got '{camera_side}'")

        # Determine pan direction: left camera pans left (negative), right pans right (positive)
        pan_sign = -1 if camera_side == 'left' else 1
        theta = math.radians(pan_sign * self.pan_angle)

        # Compute the perspective distortion factor
        tan_theta = math.tan(theta)

        # Texture-space homography for horizontal pan (yaw rotation)
        # This operates on normalized [0,1] coordinates, NOT pixels
        #
        # The homography applies perspective correction:
        #   H = [[1,    0, 0],
        #        [0,    1, 0],
        #        [h31,  0, 1]]
        #
        # where h31 = -tan(θ) for the inverse transform
        # (shader samples FROM distorted TO corrected)

        h31 = -tan_theta  # Negative for inverse transform

        # Build homography matrix (row-major order)
        homography = [
            1.0,  0.0, 0.0,  # Row 1: [1, 0, 0]
            0.0,  1.0, 0.0,  # Row 2: [0, 1, 0]
            h31,  0.0, 1.0   # Row 3: [h31, 0, 1] - perspective term
        ]

        return homography

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
