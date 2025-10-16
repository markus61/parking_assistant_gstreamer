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
        camera_spacing: float = 0.1,
        distance_to_wall: float = 4.0,
        tilt_angle: float = None
    ):
        """
        Initialize camera configuration.

        Args:
            h_fov: Horizontal field of view in degrees (default: 75.0)
            v_fov: Vertical field of view in degrees (default: 59.0)
            focal_length_mm: Camera focal length in mm (default: 2.95)
            resolution: Image resolution (width, height) in pixels (default: 1280x720)
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
        if tilt_angle is None:
            tilt_angle = self.v_fov / 2.0  # Vertical FOV / 2

        self.tilt_angle: float = tilt_angle
        self.camera_spacing: float = camera_spacing

        # Scene parameters (configurable)
        self.distance_to_object_plane: float = distance_to_wall


    def homography_matrix(self) -> list:
        """
        Compute 3x3 homography matrix for perspective correction in texture space.
        needs to be applied before rotation!
        """
        d = self.distance_to_object_plane * 1000  # Convert to mm
        cx = self.resolution[0] / 2.0  # Image center x
        cy = self.resolution[1] / 2.0  # Image center y
        alpha = math.radians(self.tilt_angle)
        efl_px = 1000 * self.focal_length_mm / 1.45
        cos_alpha = math.cos(alpha)
        sin_alpha = math.sin(alpha)
        cos_2_alpha = cos_alpha * cos_alpha
        tan_alpha = math.tan(alpha)
        one_one = d * cos_alpha / efl_px
        one_three = -d * cos_alpha * cx / efl_px
        two_two = d * cos_2_alpha / efl_px
        two_three = d*(-cy*cos_2_alpha + efl_px*sin_alpha*cos_alpha) / efl_px
        three_two = -cos_alpha * sin_alpha / efl_px
        three_three = (efl_px * cos_2_alpha + cy * sin_alpha * cos_alpha) / efl_px    

        homography = [
            one_one,  0.0, one_three, 
            0.0,  two_two, two_three,
            0.0,  three_two, three_three
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
            f"tilt_angle={self.tilt_angle}°, "
            f"distance={self.distance_to_object_plane}m)"
        )
