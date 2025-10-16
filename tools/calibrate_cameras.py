#!/usr/bin/env python3
"""
Camera calibration tool for perspective correction.

This tool helps calibrate the dual camera system by:
1. Capturing images from both cameras
2. Detecting calibration pattern (checkerboard or ArUco markers)
3. Computing accurate homography matrices
4. Computing pixel-to-meter scale from known reference object
5. Saving calibration data to config file

Requirements:
    - opencv-python (pip install opencv-python)
    - numpy (pip install numpy)

Usage:
    # Interactive calibration with live camera feed
    python src/tools/calibrate_cameras.py

    # Calibrate from saved images
    python src/tools/calibrate_cameras.py --left left.jpg --right right.jpg

    # Specify calibration pattern
    python src/tools/calibrate_cameras.py --pattern checkerboard --rows 7 --cols 9

    # Set reference object size (in meters)
    python src/tools/calibrate_cameras.py --reference-size 1.5
"""

import sys
import os
import argparse
import json
from pathlib import Path
from typing import Tuple, Optional, List

# Add parent directory to path to import camera_config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: OpenCV not installed. Install with: pip install opencv-python numpy")
    sys.exit(1)

from pylib import camera_config as cam


def detect_checkerboard(image: np.ndarray, rows: int, cols: int) -> Optional[np.ndarray]:
    """
    Detect checkerboard corners in image.

    Args:
        image: Input image (BGR)
        rows: Number of internal corners vertically
        cols: Number of internal corners horizontally

    Returns:
        Array of corner points [(x,y), ...] or None if not found
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Find checkerboard corners
    ret, corners = cv2.findChessboardCorners(gray, (cols, rows), None)

    if not ret:
        return None

    # Refine corner positions
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

    return corners.reshape(-1, 2)


def detect_aruco_markers(image: np.ndarray) -> Optional[List[np.ndarray]]:
    """
    Detect ArUco markers in image.

    Args:
        image: Input image (BGR)

    Returns:
        List of marker corner arrays or None if not found
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Use 6x6 ArUco dictionary (250 markers)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
    parameters = cv2.aruco.DetectorParameters()

    # Detect markers
    corners, ids, rejected = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=parameters)

    if ids is None or len(ids) < 4:
        return None

    return corners


def get_four_point_correspondences_interactive(image: np.ndarray, camera_name: str) -> Optional[np.ndarray]:
    """
    Interactive selection of 4 corner points from calibration target.

    User clicks 4 corners in order: top-left, top-right, bottom-right, bottom-left

    Args:
        image: Input image to display
        camera_name: Name of camera for window title

    Returns:
        Array of 4 corner points [(x,y), ...] or None if cancelled
    """
    points = []
    image_display = image.copy()

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([x, y])
            cv2.circle(image_display, (x, y), 5, (0, 255, 0), -1)
            cv2.putText(image_display, str(len(points)), (x + 10, y + 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.imshow(f"Calibrate {camera_name}", image_display)

    cv2.namedWindow(f"Calibrate {camera_name}")
    cv2.setMouseCallback(f"Calibrate {camera_name}", mouse_callback)
    cv2.imshow(f"Calibrate {camera_name}", image_display)

    print(f"\n{camera_name} camera:")
    print("Click 4 corners of calibration target in order:")
    print("  1. Top-left")
    print("  2. Top-right")
    print("  3. Bottom-right")
    print("  4. Bottom-left")
    print("Press ESC to cancel, ENTER when done")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            cv2.destroyWindow(f"Calibrate {camera_name}")
            return None
        elif key == 13 and len(points) == 4:  # ENTER
            break

    cv2.destroyWindow(f"Calibrate {camera_name}")
    return np.array(points, dtype=np.float32)


def compute_homography_from_points(image_points: np.ndarray,
                                   real_world_points: np.ndarray) -> np.ndarray:
    """
    Compute homography matrix from point correspondences.

    Args:
        image_points: 4 corner points in image [(x,y), ...]
        real_world_points: 4 corner points in real-world coords [(x,y), ...]

    Returns:
        3x3 homography matrix
    """
    H, status = cv2.findHomography(image_points, real_world_points, method=0)
    return H


def normalize_homography_for_texture_space(H: np.ndarray, image_width: int, image_height: int) -> List[float]:
    """
    Convert homography from pixel space to normalized [0,1] texture space.

    Args:
        H: 3x3 homography matrix in pixel coordinates
        image_width: Image width in pixels
        image_height: Image height in pixels

    Returns:
        9-element list in row-major order for shader
    """
    # Scaling matrices for pixel -> normalized coords
    S_inv = np.array([
        [1.0/image_width, 0, 0],
        [0, 1.0/image_height, 0],
        [0, 0, 1]
    ])

    S = np.array([
        [image_width, 0, 0],
        [0, image_height, 0],
        [0, 0, 1]
    ])

    # Convert: H_texture = S_inv * H * S
    H_texture = S_inv @ H @ S

    # Normalize by bottom-right element
    H_texture = H_texture / H_texture[2, 2]

    return H_texture.flatten().tolist()


def calibrate_camera_pair(left_image_path: Optional[str] = None,
                          right_image_path: Optional[str] = None,
                          pattern_type: str = "manual",
                          pattern_rows: int = 7,
                          pattern_cols: int = 9,
                          reference_width_meters: float = 1.5,
                          reference_height_meters: float = 1.0) -> Tuple[List[float], List[float], float]:
    """
    Calibrate both cameras using calibration pattern.

    Args:
        left_image_path: Path to left camera image (None for live capture)
        right_image_path: Path to right camera image (None for live capture)
        pattern_type: "manual", "checkerboard", or "aruco"
        pattern_rows: Checkerboard rows (internal corners)
        pattern_cols: Checkerboard columns (internal corners)
        reference_width_meters: Known width of calibration target in meters
        reference_height_meters: Known height of calibration target in meters

    Returns:
        (left_homography, right_homography, meters_per_pixel)
    """
    # Load or capture images
    if left_image_path:
        left_image = cv2.imread(left_image_path)
        if left_image is None:
            raise FileNotFoundError(f"Could not load left image: {left_image_path}")
    else:
        print("Error: Live capture not yet implemented. Provide image paths.")
        sys.exit(1)

    if right_image_path:
        right_image = cv2.imread(right_image_path)
        if right_image is None:
            raise FileNotFoundError(f"Could not load right image: {right_image_path}")
    else:
        print("Error: Live capture not yet implemented. Provide image paths.")
        sys.exit(1)

    h, w = left_image.shape[:2]

    # Real-world coordinates of calibration target corners (in meters)
    # Assuming target is at origin, with width and height as specified
    real_world_corners = np.array([
        [0, 0],                                          # Top-left
        [reference_width_meters, 0],                    # Top-right
        [reference_width_meters, reference_height_meters],  # Bottom-right
        [0, reference_height_meters]                    # Bottom-left
    ], dtype=np.float32)

    # Detect or manually select points in both images
    print("\n=== Left Camera Calibration ===")
    if pattern_type == "manual":
        left_points = get_four_point_correspondences_interactive(left_image, "Left")
    elif pattern_type == "checkerboard":
        corners = detect_checkerboard(left_image, pattern_rows, pattern_cols)
        if corners is None:
            print("Failed to detect checkerboard in left image")
            sys.exit(1)
        # Use 4 corners: top-left, top-right, bottom-right, bottom-left
        left_points = np.array([
            corners[0],
            corners[pattern_cols - 1],
            corners[-1],
            corners[-pattern_cols]
        ], dtype=np.float32)
    else:
        print(f"Pattern type '{pattern_type}' not yet implemented")
        sys.exit(1)

    if left_points is None:
        print("Calibration cancelled")
        sys.exit(1)

    print("\n=== Right Camera Calibration ===")
    if pattern_type == "manual":
        right_points = get_four_point_correspondences_interactive(right_image, "Right")
    elif pattern_type == "checkerboard":
        corners = detect_checkerboard(right_image, pattern_rows, pattern_cols)
        if corners is None:
            print("Failed to detect checkerboard in right image")
            sys.exit(1)
        right_points = np.array([
            corners[0],
            corners[pattern_cols - 1],
            corners[-1],
            corners[-pattern_cols]
        ], dtype=np.float32)

    if right_points is None:
        print("Calibration cancelled")
        sys.exit(1)

    # Compute homographies
    H_left = compute_homography_from_points(left_points, real_world_corners)
    H_right = compute_homography_from_points(right_points, real_world_corners)

    # Convert to texture space
    left_homography = normalize_homography_for_texture_space(H_left, w, h)
    right_homography = normalize_homography_for_texture_space(H_right, w, h)

    # Compute pixel scale
    # Calculate average pixel distance between corners
    left_width_pixels = np.linalg.norm(left_points[1] - left_points[0])
    left_height_pixels = np.linalg.norm(left_points[3] - left_points[0])
    avg_pixels_per_meter = (left_width_pixels / reference_width_meters +
                           left_height_pixels / reference_height_meters) / 2.0
    meters_per_pixel = 1.0 / avg_pixels_per_meter

    print(f"\nCalibration complete:")
    print(f"  Pixels per meter: {avg_pixels_per_meter:.2f}")
    print(f"  Meters per pixel: {meters_per_pixel:.6f}")

    return left_homography, right_homography, meters_per_pixel


def main():
    parser = argparse.ArgumentParser(description="Camera calibration tool for perspective correction")
    parser.add_argument("--left", type=str, help="Path to left camera image")
    parser.add_argument("--right", type=str, help="Path to right camera image")
    parser.add_argument("--pattern", type=str, default="manual",
                       choices=["manual", "checkerboard", "aruco"],
                       help="Calibration pattern type (default: manual)")
    parser.add_argument("--rows", type=int, default=7,
                       help="Checkerboard rows (internal corners, default: 7)")
    parser.add_argument("--cols", type=int, default=9,
                       help="Checkerboard columns (internal corners, default: 9)")
    parser.add_argument("--width", type=float, default=1.5,
                       help="Reference object width in meters (default: 1.5)")
    parser.add_argument("--height", type=float, default=1.0,
                       help="Reference object height in meters (default: 1.0)")
    parser.add_argument("--output", type=str, default="config/camera_calibration.json",
                       help="Output calibration file path (default: config/camera_calibration.json)")

    args = parser.parse_args()

    # Run calibration
    left_h, right_h, scale = calibrate_camera_pair(
        left_image_path=args.left,
        right_image_path=args.right,
        pattern_type=args.pattern,
        pattern_rows=args.rows,
        pattern_cols=args.cols,
        reference_width_meters=args.width,
        reference_height_meters=args.height
    )

    # Save to config
    config = cam.CameraConfig()
    config.set_calibrated_homography(left_h, right_h)
    config.calibrate_from_reference(
        reference_pixels=1.0 / scale,  # Convert meters_per_pixel to pixels_per_meter
        reference_meters=1.0
    )
    config.save_calibration(args.output)

    print(f"\nCalibration saved to: {args.output}")
    print("\nTo use this calibration, run your pipeline with:")
    print(f"  CAM_CALIBRATION_FILE={args.output} python src/i_can_see.py")


if __name__ == "__main__":
    main()
