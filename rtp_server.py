#!/usr/bin/env python3
# rtp_multicast_hevc.py
#
# Multicast stitched/cropped H.265 over RTP using GStreamer (Gst-Python).
# - Two cameras (v4l2) -> stitch (hstack) -> crop -> HW HEVC -> RTP -> UDP multicast
# - Writes an SDP file for receivers
#
# Run:
#   python3 rtp_multicast_hevc.py 
#       --dev0 /dev/video0 --dev1 /dev/video1 
#       --width 3840 --height 2160 --fps 30 
#       --maddr 239.255.0.10 --port 5004 --iface 0.0.0.0 
#       --bitrate 8000 --sdp camera.sdp
#
# Receiver (example):
#   vlc camera.sdp
#   # or: vlc "rtp://239.255.0.10:5004"

import sys
import signal
from typing import Any
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GObject", "2.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib, GObject, GstRtspServer

def build_pipeline(args: Any) -> str:
    """
    Build a pipeline string.
    """


    # Clean up double spaces and newlines for readability
    HOST="192.168.0.2"  # Multicast address
    PORT=5000

    pipeline_str = f"""
v4l2src device=/dev/video31 io-mode=4
    ! video/x-raw,format=NV12,width=1280,height=720,framerate=10/1
    ! glupload ! glcolorconvert
    ! glcolorscale
    ! 'video/x-raw,format=(string)RGBA,width=340,height=640,framerate=15/1'
    ! mix.sink_0
glvideomixer name=mix
    sink_0::xpos=0  sink_0::ypos=0 sink_0::height=640 sink_0::alpha=1.0
    sink_1::xpos=340 sink_1::ypos=0 sink_1::height=640 sink_1::alpha=1.0
    ! gldownload
    ! videoconvert ! 'video/x-raw,format=NV12'
    ! mpph265enc rc-mode=cbr bps=2000000 gop=15
    ! rtph265pay pt=96 config-interval=1 mtu=1200
    ! udpsink host=${HOST} port=${PORT} sync=false async=false qos=false
  """
    return pipeline_str

def on_bus_message(bus, msg, loop, pipeline):
    """Handle GStreamer bus messages."""
    t = msg.type
    if t == Gst.MessageType.EOS:
        print("EOS received, quitting...")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        print(f"ERROR: {err}nDEBUG: {debug}")
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        if msg.src == pipeline:
            old, new, pending = msg.parse_state_changed()
            # Print once it's playing
            if new == Gst.State.PLAYING:
                print("Pipeline is PLAYING.")
    return True


def set_perspective_matrix(pipeline: Gst.Pipeline, element_name: str, matrix: list) -> bool:
    """
    Set the matrix property of a perspective element in the pipeline.

    Args:
        pipeline: The GStreamer pipeline
        element_name: Name of the perspective element
        matrix: List of 16 float values representing a 4x4 transformation matrix

    Returns:
        True if successful, False otherwise
    """
    element = pipeline.get_by_name(element_name)
    if element is None:
        print(f"Error: Could not find element '{element_name}' in pipeline")
        return False

    try:
        element.set_property("matrix", matrix)
        print(f"Successfully set matrix for {element_name}")
        return True
    except Exception as e:
        print(f"Error setting matrix for {element_name}: {e}")
        return False


def create_keystone_matrix(top_scale: float = 1.0, bottom_scale: float = 1.0,
                          vertical_offset: float = 0.0, rotation_x: float = 0.0) -> list:
    """
    Create a keystone correction matrix for trapezoid distortion.

    Args:
        top_scale: Horizontal scaling at top of image (1.0 = no change)
        bottom_scale: Horizontal scaling at bottom of image (1.0 = no change)
        vertical_offset: Vertical position offset (-1 to 1)
        rotation_x: X-axis rotation in degrees for perspective effect

    Returns:
        List of 16 float values for 4x4 transformation matrix
    """
    # Simple keystone correction using perspective transformation
    # For trapezoid correction: top wider than bottom -> top_scale > bottom_scale

    # Convert rotation to radians
    import math
    rx = math.radians(rotation_x)

    # Create perspective transformation matrix
    # This is a simplified keystone correction matrix
    matrix = [
        top_scale,    0.0,           0.0, 0.0,
        0.0,          1.0,           0.0, 0.0,
        (top_scale - bottom_scale) * 0.5, vertical_offset, 1.0, 0.0,
        0.0,          math.sin(rx), 0.0, 1.0
    ]

    return matrix


def set_gl_transformation(pipeline: Gst.Pipeline, element_name: str,
                         top_scale: float = 1.0, bottom_scale: float = 1.0,
                         vertical_offset: float = 0.0, rotation_x: float = 0.0) -> bool:
    """
    Set keystone correction for a gltransformation element.

    Args:
        pipeline: The GStreamer pipeline
        element_name: Name of the gltransformation element
        top_scale: Horizontal scaling at top (>1.0 = wider, <1.0 = narrower)
        bottom_scale: Horizontal scaling at bottom
        vertical_offset: Vertical position adjustment
        rotation_x: X-axis rotation for perspective effect

    Returns:
        True if successful, False otherwise
    """
    element = pipeline.get_by_name(element_name)
    if element is None:
        print(f"Error: Could not find element '{element_name}' in pipeline")
        return False

    try:
        # For now, use individual properties instead of full matrix
        element.set_property("rotation-x", rotation_x)
        element.set_property("scale-x", (top_scale + bottom_scale) / 2.0)
        element.set_property("translation-y", vertical_offset)

        print(f"Successfully set GL transformation for {element_name}")
        return True
    except Exception as e:
        print(f"Error setting GL transformation for {element_name}: {e}")
        return False


if __name__ == "__main__":

    # Init GStreamer
    Gst.init(None)

    print("Launching pipeline from pipeline string:")
    print("-----------------------------------")
    pipeline_str = build_pipeline(None)
    print(pipeline_str)
    pipeline = Gst.parse_launch(pipeline_str)

    # Set initial keystone correction for camera calibration
    # Cameras are angled outward from 15m height
    # Top of image covers wider area than bottom -> keystone correction needed

    # Example values for calibration - adjust based on actual camera angles
    left_keystone = {
        "top_scale": 1.2,      # Top wider than bottom
        "bottom_scale": 0.8,   # Bottom narrower
        "vertical_offset": 0.0,
        "rotation_x": -5.0     # Slight downward angle correction
    }

    right_keystone = {
        "top_scale": 1.2,
        "bottom_scale": 0.8,
        "vertical_offset": 0.0,
        "rotation_x": -5.0
    }

    # Apply keystone correction to both cameras
    set_gl_transformation(pipeline, "transform_left", **left_keystone)
    set_gl_transformation(pipeline, "transform_right", **right_keystone)

    # Main loop & bus
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_bus_message, loop, pipeline)

    # Handle Ctrl+C
    def handle_sigint(sig, frame):
        print("Interrupted, stopping...")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    signal.signal(signal.SIGINT, handle_sigint)

    # Start
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Failed to start pipeline.", file=sys.stderr)
        sys.exit(1)

    # Example: Set perspective matrix after pipeline is playing
    # Identity matrix (no transformation)
    identity_matrix = [
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0
    ]

    # Set matrix for both perspective elements
#    set_perspective_matrix(pipeline, "perspective_left", identity_matrix)
#    set_perspective_matrix(pipeline, "perspective_right", identity_matrix)

    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)
