#!/usr/bin/env python3
import math
import numpy as np
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstGL', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)


pipeline = Gst.parse_launch(
    "videotestsrc is-live=true pattern=smpte ! "
    "video/x-raw,format=RGBA,width=1280,height=1280,framerate=30/1 ! "
    "glupload ! "
    "glimagesink sync=false"
)

test_src = pipeline.get_by_name("videotestsrc0")

# Bus logging (optional but handy)
bus = pipeline.get_bus()
assert bus is not None
bus.add_signal_watch()

def on_msg(bus, msg):
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg)
        loop.quit()
    elif t == Gst.MessageType.EOS:
        loop.quit()
bus.connect("message", on_msg)

# Start pipeline
pipeline.set_state(Gst.State.PLAYING)

# Animate: update M ~60fps
loop = GLib.MainLoop()
def rotate():
    t_now = GLib.get_monotonic_time()
    t = (t_now) / 1e6  # seconds
    angle = t * math.radians(30)  # 30 degrees per second
    c = math.cos(angle)
    s = math.sin(angle)
    M = np.array([[ c, -s, 0.0],
                  [ s,  c, 0.0],
                  [0.0, 0.0, 1.0]], dtype=np.float32)
    return M

def tick():
    pattern = test_src.get_property("pattern")
    test_src.set_property("pattern", (pattern + 1) % 26)  # wrap around to 0 after 25

    return True  # Return True to keep the timeout recurring

GLib.timeout_add_seconds(1, tick)  # Call tick() every 5 seconds
try:
    loop.run()
except KeyboardInterrupt:
    pass
finally:
    pipeline.set_state(Gst.State.NULL)
