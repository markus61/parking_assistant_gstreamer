#!/usr/bin/env python3
from os import getcwd
import numpy as np
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstGL', '1.0')
from gi.repository import GObject, Gst, GLib
from pylib import Homography2


TEST=0
CIRCLE=11

def on_msg(bus, msg):
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg)
        loop.quit()
    elif t == Gst.MessageType.EOS:
        loop.quit()


def create_mat3_uniform_structure(matrix: np.ndarray) -> Gst.Structure:
    matrix_data = matrix.flatten().tolist()
    if len(matrix_data) != 9:
        raise ValueError(f"matrix_data must contain exactly 9 floats, got {len(matrix_data)}")

    uniforms = Gst.Structure.new_empty("uniforms")

    # Map to 9 float uniforms expected by homography.frag
    names = ["m00","m01","m02","m10","m11","m12","m20","m21","m22"]
    for name, val in zip(names, matrix_data):
        uniforms.set_value(name, GObject.Value(GObject.TYPE_FLOAT, float(val)))

    # Animation-friendly defaults
    uniforms.set_value("clamp_uv", GObject.Value(GObject.TYPE_INT, 1))
    # optional: uniforms.set_value("outside_color", <add if you’ve wired vec4>)

    return uniforms

def uniforms_from_mat3(matrix: np.ndarray, name: str = "M") -> Gst.Structure:
    return create_mat3_uniform_structure(matrix)

Gst.init(None)

FRAG_120 = ""
print(getcwd())

with open("./src/shaders/homography.frag", "r") as f:
    FRAG = f.read()

with open("./src/shaders/default.vert", "r") as f:
    VERT = f.read()

###### --------> Setup pipeline <-------- ######
pipeline = Gst.parse_launch(
    "videotestsrc is-live=true pattern=smpte ! "
    "video/x-raw,format=RGBA,width=720,height=720,framerate=30/1 ! "
    "glupload ! "
    f'glshader name=warp fragment="{FRAG}" vertex="{VERT}" ! '
    "glimagesink sync=false"
)

pipeline.get_state(5 * Gst.SECOND)
pipeline.set_state(Gst.State.READY)

test_src = pipeline.get_by_name("videotestsrc0")
test_src.set_property("pattern", TEST)

warp = pipeline.get_by_name("warp")
assert isinstance(warp, Gst.Element)

h = Homography2()
h.yaw = 0.0  # degrees
h.plane_distance = 3900.0
h.camera_z = 4000.0  # mm
s = uniforms_from_mat3(h.normalized)
warp.set_property("uniforms", s )

def tick():
    h.yaw += 5.0
    s = uniforms_from_mat3(h.normalized)
    warp.set_property("uniforms", s)
    print(h)
    return True


# Bus logging (optional but handy)
bus = pipeline.get_bus()
assert bus is not None
bus.add_signal_watch()
bus.connect("message", on_msg)

# Start pipeline
pipeline.set_state(Gst.State.PLAYING)

# Animate: update M ~60fps
loop = GLib.MainLoop()

GLib.timeout_add_seconds(1, tick)  # Call tick() every 5 seconds
try:
    loop.run()
except KeyboardInterrupt:
    pass
finally:
    pipeline.set_state(Gst.State.NULL)
