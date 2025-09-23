#!/usr/bin/env python3
# rtp_multicast_hevc.py
#
# Multicast stitched/cropped H.265 over RTP using GStreamer (Gst-Python).
# - Two cameras (v4l2) -> stitch (hstack) -> crop -> HW HEVC -> RTP -> UDP multicast
# - Writes an SDP file for receivers
#
# Run:
#   python3 rtp_multicast_hevc.py \
#       --dev0 /dev/video0 --dev1 /dev/video1 \
#       --width 3840 --height 2160 --fps 30 \
#       --maddr 239.255.0.10 --port 5004 --iface 0.0.0.0 \
#       --bitrate 8000 --sdp camera.sdp
#
# Receiver (example):
#   vlc camera.sdp
#   # or: vlc "rtp://239.255.0.10:5004"

from library.configure import configure
import sys
import signal
from typing import Tuple, Any
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GObject", "2.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib, GObject, GstRtspServer

def print_sdp(addr: str, port: int, codec: str = "H265", pt: int = 96) -> None:
    """
    Minimal SDP for an RTP multicast HEVC stream.
    We rely on in-band VPS/SPS/PPS via config-interval=1 in the payloader.
    """
    print(f"""v=0
o=- 0 0 IN IP4 {addr}
s=Rock5B HEVC
c=IN IP4 {addr}
t=0 0
m=video {port} RTP/AVP {pt}
a=rtpmap:{pt} {codec}/90000
""")

def build_pipeline(args: Any) -> Tuple[Gst.Pipeline, str]:
    """
    Build a pipeline string and parse it.
    - Uses v4l2src for two cameras.
    - Stitches horizontally (hstack), then crops to desired WxH.
    - Encodes with hardware HEVC encoder.
    - Payloads to RTP (H.265) and multicasts via udpsink.
    """

    # Choose your hardware encoder element:
    #  - On many Rockchip builds: v4l2h265enc
    #  - On others (rkmpp):       mpph265enc
    hevc_enc = "v4l2h265enc"  # change to "mpph265enc" if needed

    # Input caps
    in_caps = f"video/x-raw,framerate={args.fps}/1"
    # If you know the native camera size, you can add width/height here to help the mixer.

    # Stitch side-by-side with ximages (xstack) or compositor. xstack is simple:
    # NOTE: You can replace hstack with vstack if cameras are stacked vertically.
    filter_complex = (
        f"videoconvert name=cv0 ! queue ! "
        f"videoscale ! {in_caps} ! queue, "
        f"videoconvert name=cv1 ! queue ! "
        f"videoscale ! {in_caps} ! queue "
    )

    # We’ll use the compositor element (more flexible than hstack) to place the two feeds.
    # Example: place cam0 at x=0, cam1 to its right. Adjust positions as needed.
    compositor = (
        "compositor name=mix sink_0::xpos=0 sink_0::ypos=0 sink_1::xpos=0 sink_1::ypos=0 ! "
        "videoconvert ! "
        f"videoscale ! video/x-raw,width={args.width},height={args.height},framerate={args.fps}/1 ! "
        "queue "
    )
    # If you truly want side-by-side 2x width, you could first scale each cam then place cam1 at xpos=<cam0_width>.

    # Crop (optional). If you want exact crop, set args.crop_*; otherwise pass-through.
    crop = ""
    if args.crop_w and args.crop_h:
        crop_x = args.crop_x or 0
        crop_y = args.crop_y or 0
        crop = f"videocrop left={crop_x} top={crop_y} right=0 bottom=0 ! " \
               f"videoscale ! video/x-raw,width={args.crop_w},height={args.crop_h},framerate={args.fps}/1 ! queue "

    # Encoder tuning:
    # - bitrate: kbit/s
    # - key-int (gop): fps*2 as a common baseline
    # - insert-vui: true helps some players
    # - tune=zerolatency (where supported) reduces latency
    gop = max(args.fps * 2, 30)
    enc = (
        f"{hevc_enc} bitrate={args.bitrate} key-int-max={gop} "
        f"extra-controls=controls,h265_i_frame_period={gop}:h265_profile=1 ! "  # v4l2-specific controls; safe to leave if ignored
        "h265parse config-interval=-1 ! "  # keep parameter sets, payloader will send them
        "rtph265pay name=pay config-interval=1 pt=96 ! "
        "queue leaky=2 max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! "
        f"udpsink host={args.maddr} port={args.port} ttl={args.ttl} auto-multicast=true "
        f"multicast-iface={args.iface} sync=false async=false"
    )

    # Full pipeline
    # Two sources -> convert/scale -> compositor -> (optional crop) -> encode -> RTP -> UDP multicast
    pipeline_str = f"""
        v4l2src device={args.dev0} name=cam0 !
            {in_caps} ! queue ! videoconvert ! queue ! mix.sink_0
        v4l2src device={args.dev1} name=cam1 !
            {in_caps} ! queue ! videoconvert ! queue ! mix.sink_1

        {compositor}
        {crop}
        {enc}
    """

    # Clean up double spaces and newlines for readability
    pipeline_str = " ".join(pipeline_str.split())
    return Gst.parse_launch(pipeline_str), pipeline_str

def on_bus_message(bus, msg, loop, pipeline):
    """Handle GStreamer bus messages."""
    t = msg.type
    if t == Gst.MessageType.EOS:
        print("EOS received, quitting...")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        print(f"ERROR: {err}\nDEBUG: {debug}")
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        if msg.src == pipeline:
            old, new, pending = msg.parse_state_changed()
            # Print once it's playing
            if new == Gst.State.PLAYING:
                print("Pipeline is PLAYING.")
    return True


if __name__ == "__main__":

    config = configure("pipeline")

    # Init GStreamer
    Gst.init(None)


    # Write SDP
    sdp_params = configure("sdp_params")
    print()
    print_sdp(**sdp_params)
    print()
    
    print(f"Launching pipeline: {config}")
    pipeline = Gst.parse_launch(config)

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
