
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst # type: ignore

from . import gstreamer as g

def create_pipeline() -> Gst.Pipeline:
    xvidsink = g.XVidSink()
    glvidsink = g.GlVidSink()
    glcolorconvert = g.GlColorConvert()

    original = g.Pipeline()
    #left_eye = EyePipe("left_eye")
    left_eye = g.Camera("left_eye")
    original.append(left_eye)

    # Request MJPEG from camera for 30fps
    cam_caps = g.Filter("image/jpeg,width=1280,height=720,framerate=10/1", name="cam caps")
    original.append(cam_caps)

    # Decode MJPEG to raw video
    jpegdec = g.JpegDec("jpegdec")
    original.append(jpegdec)

    # DEBUG: Check dimensions after decode
    debug1 = g.Identity("debug_1: after_jpegdec expected=1280x720").enable_caps_logging()
    original.append(debug1)

    glup = g.GlUplPipe()
    original.append(glup)
    original.append(glcolorconvert)

    # Force RGBA format with correct dimensions before tee
    force_RGBA = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1280,height=720", name="force_RGBA")
    original.append(force_RGBA)

    # DEBUG: Check dimensions after color convert
    debug2 = g.Identity("debug_2: after_glcolorconvert expected=1280x720 RGBA").enable_caps_logging()
    original.append(debug2)

    tee = g.Tee()
    original.append(tee)
    mk = g.MxPipe()
    original.append(mk)
    mk.this_sink.set_property("ypos", 720)

    distorted = tee.leg()
    distorted.append(mk)

    # Force correct mixer output dimensions (2x 1280x720 stacked = 1280x1440)
    mixer_output_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1280,height=1440", name="mixer caps")
    original.append(mixer_output_caps)

    # DEBUG: Check dimensions after mixer
    debug3 = g.Identity("debug_3: after_mixer expected=1280x1440").enable_caps_logging()
    original.append(debug3)

    # Add rotation shader between mixer and sink (stays in GL memory)
    rotate_shader = g.GlShaderRotate90(clockwise=False, name="rotate90")
    original.append(rotate_shader)

    # After rotation, dimensions are swapped: 1280x1440 → 1440x1280
    # Use Filter class to set the correct proportions after rotation
    stream_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1440,height=1280", name="stream caps")
    original.append(stream_caps)

    # DEBUG: Check dimensions after rotation
    debug4 = g.Identity("debug_4: after_rotation expected=1440x1280").enable_caps_logging()
    original.append(debug4)

    original.append(glvidsink)

    return original.pipeline

