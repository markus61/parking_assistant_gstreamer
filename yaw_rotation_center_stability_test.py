#!/usr/bin/env python3
"""
Yaw Rotation Center Stability Test — Visual Plausibility Check

Expected visuals:
- SMPTE color bars rotate smoothly around the image center
- No translation drift (center stays fixed)
- No "breathing" effect (zoom should remain constant)
- Rotation should be smooth without jitter

Setup:
- Same camera and plane as frontoparallel test
- Animate yaw from 0° to 360° in 5° increments every 0.5s
- Same output window configuration
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


class YawRotationTest:
    def __init__(self):
        self.h = None
        self.warp = None
        self.current_yaw = 0.0
        self.loop = None

    def update_uniforms(self):
        """Update yaw rotation and rebuild uniforms."""
        # Increment yaw
        self.current_yaw = (self.current_yaw + 5.0) % 360.0
        self.h.yaw = self.current_yaw

        # Rebuild uniforms
        uniforms = build_uniforms(self.h)
        self.warp.set_property("uniforms", uniforms)

        # Test center point mapping
        M = self.h.normalized
        center_in = np.array([[0.5], [0.5], [1.0]])
        center_out_h = M @ center_in
        center_out = center_out_h[:2, 0] / center_out_h[2, 0]

        print(f"yaw={self.current_yaw:6.1f}° | center maps to ({center_out[0]:.4f}, {center_out[1]:.4f}) | M[0,:]=[{M[0,0]:.4f}, {M[0,1]:.4f}, {M[0,2]:.4f}]")

        return True  # Continue timer

    def run(self):
        Gst.init(None)

        # Create Homography2 instance
        self.h = Homography2()
        self.h.cam_width = 720
        self.h.cam_height = 720

        # Camera setup: same as Test 1
        self.h.camera_x = 0.0
        self.h.camera_y = 0.0
        self.h.camera_z = 0.0  # At origin
        self.h.roll = 0.0
        self.h.pitch = 0.0
        self.h.yaw = 0.0  # Will be animated

        # Plane: same as Test 1
        # Plane: vertical wall perpendicular to camera's optical axis (+Z)
        self.h.plane_normal = [0.0, 0.0, 1.0]
        self.h.plane_distance = 4000.0

        # Output window: same as Test 1
        fx = self.h.K[0, 0]
        mm_per_px = self.h.plane_distance / fx
        out_scale = mm_per_px * self.h.cam_width

        self.h.out_scale_x_mm_per_uv = out_scale
        self.h.out_scale_y_mm_per_uv = out_scale
        self.h.out_origin_x_mm = -0.5 * out_scale
        self.h.out_origin_y_mm = -0.5 * out_scale
        self.h.y_up_src = True

        # Print initial diagnostics
        print("=== Yaw Rotation Center Stability Test ===")
        print(f"Camera: position=({self.h.camera_x}, {self.h.camera_y}, {self.h.camera_z})mm")
        print(f"Plane: normal=[{self.h.plane_normal[0,0]}, {self.h.plane_normal[1,0]}, {self.h.plane_normal[2,0]}], distance={self.h.plane_distance}mm")
        print(f"Output window: mm_per_px={mm_per_px:.3f}, out_scale={out_scale:.1f}mm")
        print(f"\nAnimating yaw in 5° increments every 0.5s...")
        print(f"Watch for: rotation around center, no drift, no zoom breathing\n")

        # Read shader files
        with open('/home/markus/src/gstreamer/src/shaders/homography.frag', 'r') as f:
            frag_shader = f.read()
        with open('/home/markus/src/gstreamer/src/shaders/default.vert', 'r') as f:
            vert_shader = f.read()

        # Build pipeline
        pipeline_desc = """
        videotestsrc is-live=true pattern=smpte !
        video/x-raw,format=RGBA,width=720,height=720,framerate=30/1 !
        glupload !
        glshader name=warp !
        glimagesink sync=false
        """

        pipeline = Gst.parse_launch(pipeline_desc)
        self.warp = pipeline.get_by_name("warp")

        # Set shaders
        self.warp.set_property("fragment", frag_shader)
        self.warp.set_property("vertex", vert_shader)

        # Set initial uniforms
        uniforms = build_uniforms(self.h)
        self.warp.set_property("uniforms", uniforms)

        # Setup timer for animation (every 500ms)
        GLib.timeout_add(500, self.update_uniforms)

        # Setup signal handlers
        self.loop = GLib.MainLoop()

        def on_message(bus, message):
            t = message.type
            if t == Gst.MessageType.EOS:
                print("\nEnd of stream")
                self.loop.quit()
            elif t == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                print(f"\nError: {err}, {debug}")
                self.loop.quit()

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", on_message)

        # Handle Ctrl-C
        def signal_handler(sig, frame):
            print("\n\nStopping...")
            pipeline.set_state(Gst.State.NULL)
            self.loop.quit()

        signal.signal(signal.SIGINT, signal_handler)

        # Start pipeline
        print("Starting pipeline... Press Ctrl-C to exit")
        pipeline.set_state(Gst.State.PLAYING)

        try:
            self.loop.run()
        finally:
            pipeline.set_state(Gst.State.NULL)

        print("Test complete")


def main():
    test = YawRotationTest()
    test.run()


if __name__ == "__main__":
    main()
