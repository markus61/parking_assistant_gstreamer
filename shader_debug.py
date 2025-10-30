#!/usr/bin/env python3

import logging
import numpy as np
import gi
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GObject, Gst, GLib  # type: ignore

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)


from pylib import Homography2
from pylib import gstreamer as g
from pylib import camera_config as cam

def create_mat3_uniform_structure(matrix: np.ndarray) -> Gst.Structure:
    """
    Creates a Gst.Structure for a mat3 uniform for the glshader element.

    Args:
        matrix_data: List of 9 floats in column-major order

    Returns:
        GstStructure with 9 float fields (m00, m01, m02, m10, m11, m12, m20, m21, m22)
    """
    matrix_data = matrix.T.flatten().tolist()
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

def on_message(bus, message, loop):
    if message.type == Gst.MessageType.ERROR:
        err, debug_info = message.parse_error()
        logger.error(f"Error received from element {message.src.get_name()}: {err.message}")
        logger.error(f"Debugging information: {debug_info if debug_info else 'none'}")
        loop.quit()
    elif message.type == Gst.MessageType.EOS:
        logger.info("End-Of-Stream reached.")
        loop.quit()

pl = g.Pipeline()
DEV = False


# Camera configuration for perspective correction
config = cam.CameraConfig()
print(f"Camera configuration: {config}")

right_eye = g.Camera("right_eye")

right_eye.element.set_property("device", "/dev/video1")
right_eye.element.set_property("io-mode", 4)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF
pl.add(right_eye)
caps_right = g.Filter("image/jpeg,width=1280,height=720,framerate=15/1",  name="right caps")
pl.append(caps_right)
# Decode MJPEG to raw video only in DEV mode
jpegdec = g.JpegDec("jpegdec")
pl.append(jpegdec)

# DEBUG: Check dimensions after decode
debug1 = g.Identity("debug_right: before_glup expected=1280x720").enable_caps_logging()
pl.append(debug1)

glup = g.GlUplPipe()
pl.append(glup)
convert = g.GlColorConvert()
pl.append(convert)

perspective_correct_right = g.GlShaderAny(name="perspective_right")
#perspective_correct_right = g.GlShaderHardCoded(name="perspective_right", matrix=h.matrix.T)
pl.append(perspective_correct_right)
h = Homography2()
h.width_src = 1280
h.height_src = 720
h.roll = 0.0
h.pitch = 0.0
h.rotation = 45.0
print(h)

s = create_mat3_uniform_structure(h.matrix)
result = perspective_correct_right.element.set_property("uniforms", s)
print(result)


cam_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1280,height=720", name="cam_caps")
#cam_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=720,height=1280", name="cam_caps")
pl.append(cam_caps)
stream_sink = g.GlVidSink()
pl.append(stream_sink)


loop = GLib.MainLoop()
bus = pl.pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message, loop)

pl.pipeline.set_state(Gst.State.PLAYING)
loop.run()

pl.pipeline.set_state(Gst.State.NULL)