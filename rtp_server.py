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
        matrix: List of 9 float values representing a 3x3 transformation matrix in row-major order

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


if __name__ == "__main__":

    # Init GStreamer
    Gst.init(sys.argv[1:])


    # Write SDP

    print("Launching pipeline from pipeline string:")
    print("-----------------------------------")
    pipeline_str = build_pipeline(None)
    print(pipeline_str)
    pipeline = Gst.parse_launch(pipeline_str)

    # Set identity matrix for perspective elements (3x3 matrix, 9 elements)
    identity_matrix = [
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0
    ]
#    set_perspective_matrix(pipeline, "perspective_left", identity_matrix)
#    set_perspective_matrix(pipeline, "perspective_right", identity_matrix)

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


    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)
