
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst # type: ignore

from . import gstreamer as g
from . import camera_config as cam

pl = g.Pipeline()
DEV = False

def left_eye_pipeline(homography: list = None) -> Gst.Pad:
    # LEFT EYE!
    # Camera caps: DEV uses MJPEG, Rock uses raw NV12
    if DEV:
        left_eye = g.TestVidSrc("left_eye")
        left_eye.element.set_property("pattern", 10)  
        left_eye.element.set_property("is-live", True)
        pl.append(left_eye)
    else:
        left_eye = g.Camera("left_eye")
        # camera props
        left_eye.element.set_property("device", "/dev/video22")
        left_eye.element.set_property("io-mode", 4)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF, 4:DMABUF-IMPORT
        pl.append(left_eye)

    left_caps = g.Filter("video/x-raw,format=NV12,width=1280,height=720,framerate=15/1", name="left caps")
    pl.append(left_caps)
    # DEBUG: Check dimensions after decode
    debug1 = g.Identity("debug_left: before_glup expected=1280x720").enable_caps_logging()
    pl.append(debug1)

    glup = g.GlUplPipe()
    pl.append(glup)
    convert = g.GlColorConvert()
    pl.append(convert)

    # Add perspective correction before rotation (if homography provided)
    if homography:
        perspective_correct = g.GlShaderHomography(homography=homography, name="perspective_left")
        pl.append(perspective_correct)

    # Add rotation shader between mixer and sink (stays in GL memory)
    rotate_shader = g.GlShaderRotate90(clockwise=False, name="rotate_left")
    pl.append(rotate_shader)
    # After rotation, dimensions are swapped: 1280x720 → 720x1280
    rotated_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=720,height=1280", name="left_rotated_caps")
    pl.append(rotated_caps)

    return pl.tail

def right_eye_pipeline(homography: list = None) -> Gst.Pad:
    # RIGHT EYE!
    right_eye = g.Camera("right_eye")

    # Camera caps: DEV uses MJPEG, Rock uses raw NV12
    if DEV:
        right_eye.element.set_property("device", "/dev/video1")
        right_eye.element.set_property("io-mode", 2)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF
        pl.add(right_eye)
        caps_right = g.Filter("image/jpeg,width=1280,height=720,framerate=15/1",  name="right caps")
        pl.append(caps_right)
        # Decode MJPEG to raw video only in DEV mode
        jpegdec = g.JpegDec("jpegdec")
        pl.append(jpegdec)
    else:
        # camera props
        right_eye.element.set_property("device", "/dev/video31")
        right_eye.element.set_property("io-mode", 4)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF, 4:DMABUF-IMPORT
        pl.add(right_eye)
        right_caps = g.Filter("video/x-raw,format=NV12,width=1280,height=720,framerate=15/1", name="right caps")
        pl.append(right_caps)
    # DEBUG: Check dimensions after decode
    debug1 = g.Identity("debug_right: before_glup expected=1280x720").enable_caps_logging()
    pl.append(debug1)

    glup = g.GlUplPipe()
    pl.append(glup)
    convert = g.GlColorConvert()
    pl.append(convert)

    # Add perspective correction before rotation (if homography provided)
    if homography:
        perspective_correct = g.GlShaderHomography(homography=homography, name="perspective_right")
        pl.append(perspective_correct)

    # Add rotation shader between mixer and sink (stays in GL memory)
    rotate_shader = g.GlShaderRotate90(clockwise=True, name="rotate_right")
    pl.append(rotate_shader)
    # After rotation, dimensions are swapped: 1280x720 → 720x1280
    rotated_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=720,height=1280", name="right_rotated_caps")
    pl.append(rotated_caps)

    return pl.tail

def create_pipeline() -> Gst.Pipeline:
    global DEV
    MACHINE = "rock"  # or "aarch64"
    try:
        rock265enc = g.Rock265Enc("rock265enc")
    except RuntimeError as e:
        if str(e) == "mpph265enc creation failed":
            MACHINE = "develop"
            DEV = True
        else:
            raise e
    print(f"Machine type detected: {MACHINE}, DEV={DEV}")

    # Camera configuration for perspective correction
    config = cam.CameraConfig()
    print(f"Camera configuration: {config}")

    homography = config.homography_matrix()
    homography = None
    left_element = left_eye_pipeline(homography=homography)
    right_eye_pipeline(homography=homography)

    # DEBUG: Check dimensions after color convert
    debug2 = g.Identity("debug_2: after glupload expected=720x1280 RGBA").enable_caps_logging()
    pl.append(debug2)

    mk = g.MxPipe()
    pl.append(mk)
    pl.tail = left_element
    pl.append(mk)
    mk.this_sink.set_property("xpos", 720)

    # After rotation, dimensions are swapped: 1280x1440 → 1440x1280
    # Use Filter class to set the correct proportions after rotation
    stream_caps = g.Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1440,height=1280", name="stream caps")
    pl.append(stream_caps)


    if DEV:
        stream_sink = g.GlVidSink()
        pl.append(stream_sink)
    else:
        # For Rock: add encoder chain before sink
        # Download from GL memory to system memory
        gldownload = g.GlDownload()
        pl.append(gldownload)

        # Convert to NV12 for encoder
        videoconvert = g.VideoConvert()
        pl.append(videoconvert)

        nv12_caps = g.Filter("video/x-raw,format=NV12", name="encoder caps")
        pl.append(nv12_caps)

        # Hardware encoder reuse from above
        rock265enc.element.set_property("rc-mode", "cbr")
        rock265enc.element.set_property("bps", 2000000)
        rock265enc.element.set_property("gop", 15)
        pl.append(rock265enc)

        # RTP payloader
        rtppay = g.RtpH265Pay("rtppay")
        rtppay.element.set_property("pt", 96)
        rtppay.element.set_property("config-interval", 1)
        rtppay.element.set_property("mtu", 1200)
        pl.append(rtppay)

        stream_sink = g.UDPSink()
        stream_sink.element.set_property("host", "192.168.0.2")
        stream_sink.element.set_property("port", 5000)
        stream_sink.element.set_property("sync", False)
        stream_sink.element.set_property("async", False)
        stream_sink.element.set_property("qos", False)
        pl.append(stream_sink)

    return pl.pipeline

