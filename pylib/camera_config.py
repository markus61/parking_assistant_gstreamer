"""
Camera configuration and homography computation for perspective correction.

This module handles camera calibration parameters and computes the homography
transformation matrices needed for perspective correction in the GStreamer pipeline.
"""

import math
import os
import json
from pathlib import Path
from typing import Tuple, Optional, Dict


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
        h_fov: Optional[float] = None,
        v_fov: Optional[float] = None,
        focal_length_mm: Optional[float] = None,
        resolution: Optional[Tuple[int, int]] = None,
        camera_height: Optional[float] = None,
        tilt_angle: Optional[float] = None,
        pan_angle: Optional[float] = None,
        camera_spacing: Optional[float] = None,
        distance_to_wall: Optional[float] = None,
        reference_object_size: Optional[float] = None,
        enable_perspective_correction: Optional[bool] = None
    ):
        """
        Initialize camera configuration.

        Parameters can be set via (in order of priority):
        1. Constructor arguments
        2. Environment variables (CAM_*)
        3. Default values

        Args:
            h_fov: Horizontal field of view in degrees (default: 75.0, env: CAM_H_FOV)
            v_fov: Vertical field of view in degrees (default: 59.0, env: CAM_V_FOV)
            focal_length_mm: Camera focal length in mm (default: 2.95, env: CAM_FOCAL_LENGTH)
            resolution: Image resolution (width, height) in pixels (default: 1280x720)
            camera_height: Height from ground in meters (default: 0.9, env: CAM_HEIGHT)
            tilt_angle: Vertical tilt in degrees, 0=horizontal (default: 0.0, env: CAM_TILT)
            pan_angle: Horizontal pan outward in degrees (default: 37.5, env: CAM_PAN)
            camera_spacing: Distance between cameras in meters (default: 0.1, env: CAM_SPACING)
            distance_to_wall: Distance to target wall in meters (default: 4.0, env: CAM_DISTANCE)
            reference_object_size: Known object size for calibration in meters (default: 0.094, env: CAM_REF_SIZE)
            enable_perspective_correction: Enable/disable perspective correction (default: True, env: CAM_PERSPECTIVE)
        """
        # Hardware intrinsics (fixed, rarely changed)
        self.h_fov: float = h_fov if h_fov is not None else float(os.getenv('CAM_H_FOV', '75.0'))
        self.v_fov: float = v_fov if v_fov is not None else float(os.getenv('CAM_V_FOV', '59.0'))
        self.focal_length_mm: float = focal_length_mm if focal_length_mm is not None else float(os.getenv('CAM_FOCAL_LENGTH', '2.95'))
        self.resolution: Tuple[int, int] = resolution if resolution is not None else (1280, 720)

        # Physical installation (configurable)
        self.camera_height: float = camera_height if camera_height is not None else float(os.getenv('CAM_HEIGHT', '0.9'))
        self.tilt_angle: float = tilt_angle if tilt_angle is not None else float(os.getenv('CAM_TILT', '0.0'))
        self.pan_angle: float = pan_angle if pan_angle is not None else float(os.getenv('CAM_PAN', '37.5'))
        self.camera_spacing: float = camera_spacing if camera_spacing is not None else float(os.getenv('CAM_SPACING', '0.1'))

        # Scene parameters (configurable)
        self.distance_to_wall: float = distance_to_wall if distance_to_wall is not None else float(os.getenv('CAM_DISTANCE', '4.0'))

        # Calibration reference
        self.reference_object_size: float = reference_object_size if reference_object_size is not None else float(os.getenv('CAM_REF_SIZE', '0.094'))

        # Perspective correction control
        self.enable_perspective_correction: bool = enable_perspective_correction if enable_perspective_correction is not None else os.getenv('CAM_PERSPECTIVE', 'true').lower() in ('true', '1', 'yes')

        # Calibrated pixel scale (computed after calibration)
        self._meters_per_pixel: Optional[float] = None

        # Calibrated homography matrices (loaded from file if available)
        self._calibrated_left_homography: Optional[list] = None
        self._calibrated_right_homography: Optional[list] = None
        self._use_calibrated_homography: bool = False

        # Try to load calibrated matrices from file
        self._load_calibration_file()

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

    def _load_calibration_file(self, calibration_path: Optional[str] = None) -> None:
        """
        Load calibrated homography matrices and scale from JSON file.

        Looks for calibration file at:
        1. Provided calibration_path
        2. Environment variable CAM_CALIBRATION_FILE
        3. Default: ./config/camera_calibration.json

        File format:
        {
            "left_homography": [h11, h12, h13, h21, h22, h23, h31, h32, h33],
            "right_homography": [h11, h12, h13, h21, h22, h23, h31, h32, h33],
            "meters_per_pixel": 0.0025
        }

        Args:
            calibration_path: Optional path to calibration file
        """
        if calibration_path is None:
            calibration_path = os.getenv('CAM_CALIBRATION_FILE', 'config/camera_calibration.json')

        cal_file = Path(calibration_path)
        if not cal_file.exists():
            return  # No calibration file, will use geometric computation

        try:
            with open(cal_file, 'r') as f:
                cal_data = json.load(f)

            # Load homography matrices
            if 'left_homography' in cal_data:
                self._calibrated_left_homography = cal_data['left_homography']
            if 'right_homography' in cal_data:
                self._calibrated_right_homography = cal_data['right_homography']

            # Load pixel scale
            if 'meters_per_pixel' in cal_data:
                self._meters_per_pixel = cal_data['meters_per_pixel']

            # Mark as using calibrated data
            if self._calibrated_left_homography and self._calibrated_right_homography:
                self._use_calibrated_homography = True
                print(f"Loaded calibrated homography matrices from {cal_file}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load calibration file {cal_file}: {e}")

    def save_calibration(self, calibration_path: str = "config/camera_calibration.json") -> None:
        """
        Save current calibration data to JSON file.

        Args:
            calibration_path: Path where to save calibration file
        """
        cal_file = Path(calibration_path)
        cal_file.parent.mkdir(parents=True, exist_ok=True)

        cal_data: Dict = {}

        # Save homography matrices if available
        if self._calibrated_left_homography:
            cal_data['left_homography'] = self._calibrated_left_homography
        if self._calibrated_right_homography:
            cal_data['right_homography'] = self._calibrated_right_homography

        # Save pixel scale if calibrated
        if self._meters_per_pixel:
            cal_data['meters_per_pixel'] = self._meters_per_pixel

        with open(cal_file, 'w') as f:
            json.dump(cal_data, f, indent=2)

        print(f"Saved calibration to {cal_file}")

    def set_calibrated_homography(self, left_homography: list, right_homography: list) -> None:
        """
        Set calibrated homography matrices manually (e.g., from calibration tool).

        Args:
            left_homography: 9-element list for left camera homography
            right_homography: 9-element list for right camera homography
        """
        if len(left_homography) != 9 or len(right_homography) != 9:
            raise ValueError("Homography matrices must be 9-element lists")

        self._calibrated_left_homography = left_homography
        self._calibrated_right_homography = right_homography
        self._use_calibrated_homography = True

    def compute_homography_matrix(self, camera_side: str) -> list:
        """
        Compute or retrieve 3x3 homography matrix for perspective correction.

        If calibrated matrices are available (from file), returns those.
        Otherwise, computes geometrically from camera parameters.

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

        # Return calibrated matrix if available
        if self._use_calibrated_homography:
            if camera_side == 'left' and self._calibrated_left_homography:
                return self._calibrated_left_homography
            elif camera_side == 'right' and self._calibrated_right_homography:
                return self._calibrated_right_homography

        # Otherwise compute geometrically
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

    def calibrate_from_reference(self, reference_pixels: float, reference_meters: float) -> None:
        """
        Calibrate pixel-to-meter scale using a known reference object.

        After perspective correction, the image should have uniform scale.
        Measure a known object in the corrected image to establish the conversion.

        Args:
            reference_pixels: Measured size of reference object in pixels
            reference_meters: Known size of reference object in meters

        Example:
            # Measure a 1.5m wide object in the corrected image
            config.calibrate_from_reference(reference_pixels=800, reference_meters=1.5)
        """
        self._meters_per_pixel = reference_meters / reference_pixels

    @property
    def meters_per_pixel(self) -> Optional[float]:
        """
        Get calibrated meters-per-pixel scale factor.

        Returns None if not yet calibrated via calibrate_from_reference().
        After calibration, use pixels_to_meters() for conversions.
        """
        return self._meters_per_pixel

    def pixels_to_meters(self, pixel_distance: float) -> float:
        """
        Convert pixel distance to real-world meters.

        Requires prior calibration via calibrate_from_reference().
        Works only on perspective-corrected images with uniform scale.

        Args:
            pixel_distance: Distance in pixels (after perspective correction)

        Returns:
            Distance in meters

        Raises:
            RuntimeError: If not calibrated yet
        """
        if self._meters_per_pixel is None:
            raise RuntimeError(
                "Not calibrated. Call calibrate_from_reference() first with a known reference object."
            )
        return pixel_distance * self._meters_per_pixel

    def meters_to_pixels(self, meter_distance: float) -> float:
        """
        Convert real-world meters to pixel distance.

        Requires prior calibration via calibrate_from_reference().
        Works only on perspective-corrected images with uniform scale.

        Args:
            meter_distance: Distance in meters

        Returns:
            Distance in pixels (in corrected image)

        Raises:
            RuntimeError: If not calibrated yet
        """
        if self._meters_per_pixel is None:
            raise RuntimeError(
                "Not calibrated. Call calibrate_from_reference() first with a known reference object."
            )
        return meter_distance / self._meters_per_pixel

    def __repr__(self) -> str:
        """String representation of camera configuration."""
        cal_status = f", calibrated={self._meters_per_pixel is not None}" if self._meters_per_pixel is not None else ""
        return (
            f"CameraConfig(h_fov={self.h_fov}°, v_fov={self.v_fov}°, "
            f"resolution={self.resolution}, "
            f"pan_angle={self.pan_angle}°, spacing={self.camera_spacing}m, "
            f"distance={self.distance_to_wall}m{cal_status})"
        )
