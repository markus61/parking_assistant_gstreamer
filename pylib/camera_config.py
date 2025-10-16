"""
Camera configuration and homography computation for bird's-eye view perspective correction.

This module handles camera calibration parameters and computes the homography
transformation matrices needed for perspective correction in the GStreamer pipeline.
"""

import math
from typing import Tuple


class CameraConfig:
    """
    Camera configuration for dual Radxa 4K cameras with perspective correction.
    
    This class calculates the homography matrix required to transform the camera's
    perspective view into a top-down "bird's-eye" view of the ground plane.

    Camera specifications (Radxa 4K):
        - Focal Length: 2.95mm
        - Pixel Pitch: 1.45µm
        - Vertical FOV (after 90° rotation): 59°
        - Resolution: 1280x720 pixels

    The homography is calculated based on the camera's focal length, resolution,
    tilt angle, and its height above the ground plane.

    Usage:
        config = CameraConfig()
        h_matrix = config.homography_matrix()
    """

    def __init__(
        self,
        v_fov: float = 59.0,
        focal_length_mm: float = 2.95, # Radxa 4K camera spec
        pixel_pitch_um: float = 1.45,  # Radxa 4K camera spec
        resolution: Tuple[int, int] = (1280, 720),
        camera_spacing: float = 0.1,
        distance_to_wall: float = 4.0,
        tilt_angle: float = None
    ):
        """
        Initialize camera configuration for bird's-eye view.

        Args:
            v_fov: Vertical field of view in degrees (used for default tilt)
            focal_length_mm: Camera focal length in mm (default: 2.95)
            pixel_pitch_um: Sensor pixel pitch in micrometers (default: 1.45)
            resolution: Image resolution (width, height) in pixels (default: 1280x720)
            camera_spacing: Distance between cameras in meters (default: 0.1)
            distance_to_wall: Distance to target wall in meters (default: 4.0)
            tilt_angle: Vertical tilt in degrees, 0=horizontal. If None, it's
                        calculated to place the horizon at the top of the image.
        """
        # Camera intrinsics
        self.v_fov: float = v_fov
        self.focal_length_mm: float = focal_length_mm
        self.pixel_pitch_um: float = pixel_pitch_um
        self.resolution: Tuple[int, int] = resolution

        # Physical installation parameters
        if tilt_angle is None:
            # Default tilt to place the horizon at the top edge of the image.
            # A tilt of 0° is horizontal, 90° is looking straight down.
            tilt_angle = self.v_fov / 2.0

        self.tilt_angle: float = tilt_angle
        self.camera_spacing: float = camera_spacing

        # Scene parameters
        self.distance_to_object_plane: float = distance_to_wall


    def homography_matrix(self) -> list:
        """
        Compute 3x3 homography matrix for bird's-eye view transformation.

        This matrix maps points from the destination image (the desired top-down
        view) back to the source image (the original camera perspective). It is
        intended for use in a GLSL shader that performs inverse texture mapping.
        """
        w, h = self.resolution
        cx, cy = w / 2.0, h / 2.0

        # Focal length in pixels, calculated from physical specs.
        fy = (self.focal_length_mm * 1000) / self.pixel_pitch_um

        # Camera tilt angle in radians (0=horizontal, positive=downward)
        alpha = math.radians(self.tilt_angle)
        sa, ca = math.sin(alpha), math.cos(alpha)

        # Camera height in meters (distance to the object plane)
        H = self.distance_to_object_plane

        # Build the homography matrix H that maps destination (bird's-eye)
        # coordinates back to source (perspective) coordinates.

        homography = [
            1.0, 0.0,     -cx,
            0.0, sa / fy, cy - (H * ca) / fy,
            0.0, ca / H,  sa
        ]

        return homography

    def __repr__(self) -> str:
        """String representation of camera configuration."""
        return (
            f"CameraConfig(v_fov={self.v_fov}°, "
            f"resolution={self.resolution}, "
            f"tilt_angle={self.tilt_angle}°, "
            f"distance={self.distance_to_object_plane}m)"
        )
