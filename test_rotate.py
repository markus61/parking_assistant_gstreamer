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
    """
    Creates a Gst.Structure for a mat3 uniform for the glshader element.

    Args:
        matrix_data: List of 9 floats in column-major order

    Returns:
        GstStructure with 9 float fields (m00, m01, m02, m10, m11, m12, m20, m21, m22)
    """
    matrix_data = matrix.flatten().tolist()
    if len(matrix_data) != 9:
        raise ValueError(f"matrix_data must contain exactly 9 floats, got {len(matrix_data)}")

    # Create the uniforms structure with 9 individual float fields
    uniforms = Gst.Structure.new_empty("uniforms")

    # Set each matrix element as an individual float uniform (column-major order)
    # Must use explicit GObject.TYPE_FLOAT to avoid double conversion
    uniform_names = ["m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22"]
    for name, val in zip(uniform_names, matrix_data):
        uniforms.set_value(name, GObject.Value(GObject.TYPE_FLOAT, float(val)))
    
    uniforms.set_value("clamp_uv", GObject.Value(GObject.TYPE_INT, 0))

    return uniforms

def uniforms_from_mat3(matrix: np.ndarray, name: str = "M") -> Gst.Structure:
    return create_mat3_uniform_structure(matrix)

Gst.init(None)

FRAG_120 = ""
print(getcwd())

with open("./src/shaders/rotate.frag", "r") as f:
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
test_src.set_property("pattern", CIRCLE)

warp = pipeline.get_by_name("warp")
assert isinstance(warp, Gst.Element)

H = Homography2()
H.rotation = 0.0  # degrees
s = uniforms_from_mat3(H.matrix)
warp.set_property("uniforms", s )

def tick():
    H.rotation += 10.0
    s = uniforms_from_mat3(H.matrix)
    warp.set_property("uniforms", s)
    print(H)
    return True



fragment = warp.get_property("fragment")  # Force property initialization
uniforms = warp.get_property("uniforms")  # Force property initialization
context = warp.get_property("context")  # Force GL context initialization
shader = warp.get_property("shader")  # Force shader initialization

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
