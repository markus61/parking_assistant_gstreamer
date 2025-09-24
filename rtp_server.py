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
from typing import Tuple, Any
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
    LEFT="/dev/video31"
    RIGHT="/dev/video22"

    FRAMES=30
    pipeline_str = f"""
  compositor name=stitch background=black start-time-selection=zero latency=0
    sink_0::xpos=0    sink_0::ypos=0 sink_0::width=540 sink_0::height=960
    sink_1::xpos=540 sink_1::ypos=0 sink_1::width=540 sink_1::height=960
  ! videorate drop-only=true max-rate={FRAMES}
  ! video/x-raw,format=NV12,width=1080,height=960,framerate={FRAMES}/1
  ! queue max-size-buffers=2 max-size-time=33333333 leaky=2
  ! mpph265enc rc-mode=cbr bps=6000000 bps-min=4000000 bps-max=8000000 gop=15
  ! h265parse config-interval=-1
  ! rtph265pay pt=96 config-interval=1 mtu=1460
  ! udpsink host={HOST} port={PORT} sync=false async=false qos=false

  v4l2src device={LEFT} io-mode=4
  ! video/x-raw,format=NV12,width=1920,height=1080,framerate={FRAMES}/1
  ! videocrop name=transform_left
  ! videoflip method=counterclockwise
  ! queue max-size-buffers=2 max-size-time=33333333 leaky=2
  ! stitch.sink_0

  v4l2src device={RIGHT} io-mode=4
  ! video/x-raw,format=NV12,width=1920,height=1080,framerate={FRAMES}/1
  ! videocrop name=transform_right
  ! videoflip method=clockwise
  ! queue max-size-buffers=2 max-size-time=33333333 leaky=2
  ! stitch.sink_1
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


def set_crop_keystone(pipeline: Gst.Pipeline, element_name: str,
                     top_crop: int = 0, bottom_crop: int = 0,
                     left_crop: int = 0, right_crop: int = 0) -> bool:
    """
    Set cropping-based keystone correction for a videocrop element.
    This is a simplified approach that crops different amounts from each edge.

    Args:
        pipeline: The GStreamer pipeline
        element_name: Name of the videocrop element
        top_crop: Pixels to crop from top
        bottom_crop: Pixels to crop from bottom
        left_crop: Pixels to crop from left
        right_crop: Pixels to crop from right

    Returns:
        True if successful, False otherwise
    """
    element = pipeline.get_by_name(element_name)
    if element is None:
        print(f"Error: Could not find element '{element_name}' in pipeline")
        return False

    try:
        element.set_property("top", top_crop)
        element.set_property("bottom", bottom_crop)
        element.set_property("left", left_crop)
        element.set_property("right", right_crop)

        print(f"Successfully set crop keystone for {element_name}: top={top_crop}, bottom={bottom_crop}, left={left_crop}, right={right_crop}")
        return True
    except Exception as e:
        print(f"Error setting crop keystone for {element_name}: {e}")
        return False


if __name__ == "__main__":

    # Init GStreamer
    Gst.init(None)


    # Write SDP

    print("Launching pipeline from pipeline string:")
    print("-----------------------------------")
    pipeline_str = build_pipeline(None)
    print(pipeline_str)
    pipeline = Gst.parse_launch(pipeline_str)

    # Set initial cropping-based keystone correction for camera calibration
    # Cameras are angled outward from 15m height
    # Top of image covers wider area than bottom -> crop to compensate for trapezoid

    # Example: crop more from sides at top, less at bottom to create rectangular view
    # Adjust these values based on actual camera mounting angles
    left_crop_settings = {
        "top_crop": 50,      # Crop from top
        "bottom_crop": 20,   # Less crop from bottom
        "left_crop": 100,    # Crop from left side
        "right_crop": 50     # Less crop from right
    }

    right_crop_settings = {
        "top_crop": 50,
        "bottom_crop": 20,
        "left_crop": 50,     # Less crop from left
        "right_crop": 100    # More crop from right
    }

    # Apply cropping-based keystone correction
    set_crop_keystone(pipeline, "transform_left", **left_crop_settings)
    set_crop_keystone(pipeline, "transform_right", **right_crop_settings)

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
