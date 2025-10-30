#!/usr/bin/env python3
"""
Ground Plane Oblique Test — Visual Plausibility Check

Expected visuals:
- Checkerboard pattern viewed from above at an angle
- Foreshortening toward the top (away from camera)
- Straight grid lines remain straight (no curvature)
- Bottom of image appears closer, top appears farther
- Perspective looks physically plausible

Setup:
- Camera 12m above ground, pitched downward 60°
- Horizontal ground plane (Z=0, normal pointing up)
- Output window spans ~5m x 5m on ground
"""

import sys
import signal
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import numpy as np

# Add pylib to path
sys.path.insert(0, '/home/markus/src/gstreamer/src')
from pylib.homography import Homography2


def build_uniforms(h: Homography2) -> Gst.Structure:
    """Build GStreamer uniform structure from Homography2.normalized.

    Note: Due to how the shader reconstructs the matrix from uniforms,
    the row-major flatten pattern effectively transposes the matrix.
    This matches the behavior in test_rotate.py.
    """
    from gi.repository import GObject
    M = h.normalized

    uniforms = Gst.Structure.new_empty("uniforms")

    # Flatten in row-major order (NumPy default)
    matrix_data = M.flatten().tolist()
    names = ["m00","m01","m02","m10","m11","m12","m20","m21","m22"]

    for name, val in zip(names, matrix_data):
        uniforms.set_value(name, GObject.Value(GObject.TYPE_FLOAT, float(val)))

    uniforms.set_value("clamp_uv", GObject.Value(GObject.TYPE_INT, 1))

    return uniforms


def main():
    Gst.init(None)

    # Create Homography2 instance
    h = Homography2()
    h.cam_width = 720
    h.cam_height = 720

    # Camera setup: 12m above ground, looking straight down
    # NOTE: Camera optical axis points +Z (up) by default, so roll=180° flips it downward
    h.camera_x = 0.0
    h.camera_y = 0.0
    h.camera_z = 12000.0  # 12 meters above ground
    h.pitch = -60.0
    h.yaw = 0.0

    # Plane: horizontal ground, normal pointing up (+Z)
    h.plane_normal = [0.0, 0.0, 1.0]  # Z-axis (up)
    h.plane_distance = 1.0  # 1mm (small positive value to satisfy |d|≥EPS)

    # Output window: span 5m x 5m on ground, centered
    h.out_scale_x_mm_per_uv = 5000.0  # 5 meters per UV unit
    h.out_scale_y_mm_per_uv = 5000.0
    h.out_origin_x_mm = -2500.0  # Center the 5m span
    h.out_origin_y_mm = 18286.341
    h.y_up_src = True  # GL UV convention

    # Print diagnostics
    print("=== Ground Plane Oblique Test ===")
    print(f"Camera: position=({h.camera_x}, {h.camera_y}, {h.camera_z})mm (12m high)")
    print(f"Camera: roll={h.roll}°, pitch={h.pitch}°, yaw={h.yaw}°")
    print(f"Plane: normal=[{h.plane_normal[0,0]}, {h.plane_normal[1,0]}, {h.plane_normal[2,0]}] (horizontal, up)")
    print(f"Plane: distance={h.plane_distance}mm")
    print(f"Output window: {h.out_scale_x_mm_per_uv}mm x {h.out_scale_y_mm_per_uv}mm (5m x 5m)")
    print(f"Output origin: ({h.out_origin_x_mm}mm, {h.out_origin_y_mm}mm)")

    # Get normalized matrix
    M = h.normalized
    x = np.array([0.5, 0.5, 1.0], dtype=np.float32)
    uvw = M @ x
    uv = uvw[:2] / uvw[2]
    print("center maps to", uv)  # should be ~[0.5, 0.5]
    print(f"\nM[0,:] = [{M[0,0]:.6f}, {M[0,1]:.6f}, {M[0,2]:.6f}]")
    print(f"M[1,:] = [{M[1,0]:.6f}, {M[1,1]:.6f}, {M[1,2]:.6f}]")
    print(f"M[2,:] = [{M[2,0]:.6f}, {M[2,1]:.6f}, {M[2,2]:.6f}]")

    # Test center point mapping
    center_in = np.array([[0.5], [0.5], [1.0]])
    center_out_h = M @ center_in
    center_out = center_out_h[:2, 0] / center_out_h[2, 0]
    print(f"\nCenter (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")

    # Sample horizontal line to check for monotonicity
    print("\nHorizontal line sampling (checking for monotonicity):")
    print("UV_in (y=0.5)  →  UV_out")
    for x in np.linspace(0.0, 1.0, 9):
        point_in = np.array([[x], [0.5], [1.0]])
        point_out_h = M @ point_in
        point_out = point_out_h[:2, 0] / point_out_h[2, 0]
        print(f"  ({x:.2f}, 0.50)  →  ({point_out[0]:.4f}, {point_out[1]:.4f})")

    # Read shader files
    with open('/home/markus/src/gstreamer/src/shaders/homography.frag', 'r') as f:
        frag_shader = f.read()
    with open('/home/markus/src/gstreamer/src/shaders/default.vert', 'r') as f:
        vert_shader = f.read()

    # Build pipeline
    pipeline_desc = """
    videotestsrc is-live=true pattern=checkers-1 !
    video/x-raw,format=RGBA,width=720,height=720,framerate=30/1 !
    glupload !
    glshader name=warp !
    glimagesink sync=false
    """

    pipeline = Gst.parse_launch(pipeline_desc)
    warp = pipeline.get_by_name("warp")

    # Set shaders
    warp.set_property("fragment", frag_shader)
    warp.set_property("vertex", vert_shader)

    # Set uniforms
    uniforms = build_uniforms(h)
    warp.set_property("uniforms", uniforms)

    # Setup signal handlers
    loop = GLib.MainLoop()

    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("\nEnd of stream")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\nError: {err}, {debug}")
            loop.quit()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    # Handle Ctrl-C
    def signal_handler(sig, frame):
        print("\n\nStopping...")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()

    signal.signal(signal.SIGINT, signal_handler)

    # Start pipeline
    print("\nStarting pipeline... Press Ctrl-C to exit")
    print("Expected: Checkerboard foreshortened toward top, straight lines stay straight\n")
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)

    print("Test complete")


if __name__ == "__main__":
    main()
