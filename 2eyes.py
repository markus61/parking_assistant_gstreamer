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
    ! 'video/x-raw,format=(string)RGBA,width=340,height=640,framerate=10/1'
    ! mix.sink_0
v4l2src device=/dev/video22 io-mode=4
    ! video/x-raw,format=NV12,width=1280,height=720,framerate=10/1
    ! glupload ! glcolorconvert
    ! glcolorscale
    ! 'video/x-raw,format=(string)RGBA,width=340,height=640,framerate=10/1'
    ! mix.sink_1
glvideomixer name=mix
    sink_0::xpos=0  sink_0::ypos=0 sink_0::height=640 sink_0::alpha=1.0
    sink_1::xpos=340 sink_1::ypos=0 sink_1::height=640 sink_1::alpha=1.0
    ! gldownload
    ! videoconvert ! 'video/x-raw,format=NV12,framerate=10/1'
    ! mpph265enc rc-mode=cbr bps=2000000 gop=15
    ! rtph265pay pt=96 config-interval=1 mtu=1200
    ! udpsink host={HOST} port={PORT} sync=false async=false qos=false
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
def create_pipeline():
    HOST = "192.168.0.2"
    PORT = 5000

    # Create pipeline
    pipeline = Gst.Pipeline.new("2eyes-pipeline")

    # Create elements - Camera 0 branch
    v4l2src0 = Gst.ElementFactory.make("v4l2src", "cam0")
    v4l2src0.set_property("device", "/dev/video31")
    v4l2src0.set_property("io-mode", 4)

    caps0 = Gst.Caps.from_string("video/x-raw,format=NV12,width=1280,height=720,framerate=10/1")
    capsfilter0 = Gst.ElementFactory.make("capsfilter", "caps0")
    capsfilter0.set_property("caps", caps0)

    glupload0 = Gst.ElementFactory.make("glupload", "glupload0")
    glcolorconvert0 = Gst.ElementFactory.make("glcolorconvert", "glcolorconvert0")
    glcolorscale0 = Gst.ElementFactory.make("glcolorscale", "glcolorscale0")

    caps0_scale = Gst.Caps.from_string("video/x-raw,format=(string)RGBA,width=340,height=640,framerate=10/1")
    capsfilter0_scale = Gst.ElementFactory.make("capsfilter", "caps0_scale")
    capsfilter0_scale.set_property("caps", caps0_scale)

    # Create elements - Camera 1 branch
    v4l2src1 = Gst.ElementFactory.make("v4l2src", "cam1")
    v4l2src1.set_property("device", "/dev/video22")
    v4l2src1.set_property("io-mode", 4)

    caps1 = Gst.Caps.from_string("video/x-raw,format=NV12,width=1280,height=720,framerate=10/1")
    capsfilter1 = Gst.ElementFactory.make("capsfilter", "caps1")
    capsfilter1.set_property("caps", caps1)

    glupload1 = Gst.ElementFactory.make("glupload", "glupload1")
    glcolorconvert1 = Gst.ElementFactory.make("glcolorconvert", "glcolorconvert1")
    glcolorscale1 = Gst.ElementFactory.make("glcolorscale", "glcolorscale1")

    caps1_scale = Gst.Caps.from_string("video/x-raw,format=(string)RGBA,width=340,height=640,framerate=10/1")
    capsfilter1_scale = Gst.ElementFactory.make("capsfilter", "caps1_scale")
    capsfilter1_scale.set_property("caps", caps1_scale)

    # Create mixer
    mixer = Gst.ElementFactory.make("glvideomixer", "mix")

    # Create output branch
    gldownload = Gst.ElementFactory.make("gldownload", "gldownload")
    videoconvert = Gst.ElementFactory.make("videoconvert", "videoconvert")

    caps_output = Gst.Caps.from_string("video/x-raw,format=NV12,framerate=10/1")
    capsfilter_output = Gst.ElementFactory.make("capsfilter", "caps_output")
    capsfilter_output.set_property("caps", caps_output)

    encoder = Gst.ElementFactory.make("mpph265enc", "encoder")
    encoder.set_property("rc-mode", "cbr")
    encoder.set_property("bps", 2000000)
    encoder.set_property("gop", 15)

    payloader = Gst.ElementFactory.make("rtph265pay", "payloader")
    payloader.set_property("pt", 96)
    payloader.set_property("config-interval", 1)
    payloader.set_property("mtu", 1200)

    udpsink = Gst.ElementFactory.make("udpsink", "udpsink")
    udpsink.set_property("host", HOST)
    udpsink.set_property("port", PORT)
    udpsink.set_property("sync", False)
    udpsink.set_property("async", False)
    udpsink.set_property("qos", False)

    # Add all elements to pipeline
    pipeline.add(v4l2src0, capsfilter0, glupload0, glcolorconvert0, glcolorscale0, capsfilter0_scale)
    pipeline.add(v4l2src1, capsfilter1, glupload1, glcolorconvert1, glcolorscale1, capsfilter1_scale)
    pipeline.add(mixer, gldownload, videoconvert, capsfilter_output, encoder, payloader, udpsink)

    # Link camera 0 branch
    v4l2src0.link(capsfilter0)
    capsfilter0.link(glupload0)
    glupload0.link(glcolorconvert0)
    glcolorconvert0.link(glcolorscale0)
    glcolorscale0.link(capsfilter0_scale)

    # Link camera 1 branch
    v4l2src1.link(capsfilter1)
    capsfilter1.link(glupload1)
    glupload1.link(glcolorconvert1)
    glcolorconvert1.link(glcolorscale1)
    glcolorscale1.link(capsfilter1_scale)

    # Link camera branches to mixer with pad properties
    sink_pad_0 = mixer.request_pad_simple("sink_%u")
    sink_pad_0.set_property("xpos", 0)
    sink_pad_0.set_property("ypos", 0)
    sink_pad_0.set_property("height", 640)
    sink_pad_0.set_property("alpha", 1.0)
    src_pad_0 = capsfilter0_scale.get_static_pad("src")
    link_result_0 = src_pad_0.link(sink_pad_0)
    if link_result_0 != Gst.PadLinkReturn.OK:
        print(f"Failed to link camera 0 to mixer: {link_result_0}")

    sink_pad_1 = mixer.request_pad_simple("sink_%u")
    sink_pad_1.set_property("xpos", 340)
    sink_pad_1.set_property("ypos", 0)
    sink_pad_1.set_property("height", 640)
    sink_pad_1.set_property("alpha", 1.0)
    src_pad_1 = capsfilter1_scale.get_static_pad("src")
    link_result_1 = src_pad_1.link(sink_pad_1)
    if link_result_1 != Gst.PadLinkReturn.OK:
        print(f"Failed to link camera 1 to mixer: {link_result_1}")

    # Link output branch
    mixer.link(gldownload)
    gldownload.link(videoconvert)
    videoconvert.link(capsfilter_output)
    capsfilter_output.link(encoder)
    encoder.link(payloader)
    payloader.link(udpsink)

    return pipeline

if __name__ == "__main__":

    # Init GStreamer
    Gst.init(None)

    print("Launching pipeline from pipeline string:")
    print("-----------------------------------")
    pipeline_str = build_pipeline(None)
    print(pipeline_str)
    pipeline = create_pipeline()

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
