
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst # type: ignore

from . import gstreamer as g

def create_pipeline() -> Gst.Pipeline:
    MACHINE = "rock"  # or "aarch64"
    DEV = False
    try:
        rock265enc = g.Rock265Enc("rock265enc")
    except RuntimeError as e:
        if str(e) == "mpph265enc creation failed":
            MACHINE = "develop"
            DEV = True
        else:
            raise e

    left_eye = g.Camera("left_eye")
    if DEV:
        stream_sink = g.GlVidSink()
        # Disable aspect ratio forcing to fill the window without black bars
        stream_sink.element.set_property("force-aspect-ratio", False)
        # camera props
        left_eye.element.set_property("device", "/dev/video1")
        left_eye.element.set_property("io-mode", 2)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF
    else:
        stream_sink = g.UDPSink()
        stream_sink.element.set_property("host", "192.168.0.2")
        stream_sink.element.set_property("port", 5000)
        stream_sink.element.set_property("sync", False)
        # camera props
        left_eye.element.set_property("device", "/dev/video22")
        left_eye.element.set_property("io-mode", 4)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF


    glcolorconvert = g.GlColorConvert()

    original = g.Pipeline()
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

    original.append(stream_sink)

    return original.pipeline

