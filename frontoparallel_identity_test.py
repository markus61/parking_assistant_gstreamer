#!/usr/bin/env python3
"""
Fronto-parallel Wall Test — Visual Plausibility Check

Expected visuals:
- Checkerboard pattern should appear centered and undistorted
- Squares remain squares (no shear or rotation)
- Minimal uniform zoom is acceptable
- Image should be stable (not breathing or drifting)

Setup:
- Camera at origin looking at wall 4m away (X=4000mm)
- Zero rotation (roll=pitch=yaw=0)
- Vertical wall perpendicular to X-axis
- Output window sized to span central field of view
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

    # Camera setup: at origin, looking at wall 4m away
    # With +X forward, +Y right, +Z up: camera at origin looks along +X axis
    h.camera_x = 0.0
    h.camera_y = 0.0
    h.camera_z = 0.0  # At origin (not elevated)
    h.roll = 0.0
    h.pitch = 0.0
    h.yaw = 0.0

    # Plane: vertical wall perpendicular to camera's optical axis
    # Camera optical axis is +Z (up), so plane normal is +Z
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
    h.y_up_src = True  # GL UV convention

    # Print diagnostics
    print("=== Fronto-parallel Identity Test ===")
    print(f"Camera: position=({h.camera_x}, {h.camera_y}, {h.camera_z})mm")
    print(f"Camera: roll={h.roll}°, pitch={h.pitch}°, yaw={h.yaw}°")
    print(f"Plane: normal={[h.plane_normal[i,0] for i in range(3)]}, distance={h.plane_distance}mm")
    print(f"Output window: mm_per_px={mm_per_px:.3f}, out_scale={out_scale:.1f}mm")
    print(f"Output origin: ({h.out_origin_x_mm:.1f}, {h.out_origin_y_mm:.1f})mm")

    # Get normalized matrix
    M = h.normalized
    print(f"M[0,:] = [{M[0,0]:.6f}, {M[0,1]:.6f}, {M[0,2]:.6f}]")

    # Test center point mapping
    center_in = np.array([[0.5], [0.5], [1.0]])
    center_out_h = M @ center_in
    center_out = center_out_h[:2, 0] / center_out_h[2, 0]
    print(f"Center (0.5,0.5) maps to ({center_out[0]:.4f}, {center_out[1]:.4f})")

    # Read shader files
    with open('/home/markus/src/gstreamer/src/shaders/homography.frag', 'r') as f:
        frag_shader = f.read()
    with open('/home/markus/src/gstreamer/src/shaders/default.vert', 'r') as f:
        vert_shader = f.read()

    # Build pipeline
    pipeline_desc = f"""
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
            print("End of stream")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            loop.quit()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    # Handle Ctrl-C
    def signal_handler(sig, frame):
        print("\nStopping...")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()

    signal.signal(signal.SIGINT, signal_handler)

    # Start pipeline
    print("\nStarting pipeline... Press Ctrl-C to exit")
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)

    print("Test complete")


if __name__ == "__main__":
    main()
