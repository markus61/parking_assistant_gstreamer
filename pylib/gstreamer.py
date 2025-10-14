import sys
import gi
import logging

gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gst, GLib, GObject  # type: ignore

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

# Initialize GStreamer
Gst.init(sys.argv[1:])

class GstElement():
    """Base wrapper for GStreamer elements. Provides name, src/sink pads, and linking."""
    def __init__(self, element: str, name: str):
        self.element = Gst.ElementFactory.make(element, name)
        self._name = self.element.get_name() if self.element else ""
        self.pipeline = None

    @property
    def name(self) -> str:
        return self._name
    @property
    def src(self) -> Gst.Element:
        return self.element.get_static_pad("src")
    
    @property
    def sink(self) -> Gst.Element:
        return self.element.get_static_pad("sink")

    def link(self, sink) -> Gst.Element:            
        return self.src.link(sink)


class Pipeline():
    """
    GStreamer pipeline wrapper with automatic element linking.
    Use append() to add elements sequentially.
    """
    def __init__(self, element: GstElement = None, name: str = None ):
        self.tail = None
        if element and element.pipeline:
            self.pipeline = element.pipeline
        else:
            self.pipeline = Gst.Pipeline.new(name) or None
        if element:
            self.tail = element
            if self.pipeline.get_by_name(element.name) is None:
                self.pipeline.add(element.element)
 
    @property
    def gst_pipeline(self) -> Gst.Pipeline:
        return self.pipeline
    
    def walk_pattern(self, name:str) -> bool:
        element = self.pipeline.get_by_name(name)
        pattern = int(element.props.pattern)
        pattern = pattern + 1
        if pattern == 23:
            # Send EOS to stop the pipeline gracefully
            self.pipeline.send_event(Gst.Event.new_eos())
            return None
        element.set_property("pattern", pattern)
        print(f"Pattern {pattern}")
        return pattern

    def append(self, element: GstElement):
        self.pipeline.add(element.element)
        element.pipeline = self.pipeline
        type_name = element.element.__gtype__.name

        if self.tail is None:
            self.tail = element
            return self

        # Link tail to new element
        link_result = self.tail.src.link(element.sink)

        # Check if link was successful
        if link_result != Gst.PadLinkReturn.OK:
            logger.error(f"Failed to link {self.tail.name} -> {element.name}: {link_result}")
            raise RuntimeError(f"Pad linking failed: {link_result}")

        logger.debug(f"Linked {self.tail.name} -> {element.name}")
        self.tail = element
        return self

    def cleanup(self):
        """Sets the pipeline to NULL state to stop it and free resources."""
        if self.pipeline:
            print("Stopping pipeline and releasing resources...")
            
            # 1. Set the state to NULL
            # This is the equivalent of "removing" the pipeline.
            self.pipeline.set_state(Gst.State.NULL)
            
            print("Pipeline stopped.")

class MxPipe(GstElement):
    """
    GL video mixer with multiple inputs. Compositor for OpenGL memory.
    Position inputs using sink pad properties: this_sink.set_property("xpos", x)
    Requires video/x-raw(memory:GLMemory) input format.
    """
    def __init__(self, name: str = None):
        super().__init__("glvideomixer", name)
        self.sinks = 0
        self.this_sink = None

    @property
    def sink(self) -> Gst.Element:
        _sink = self.element.get_request_pad("sink_%u")
        if _sink:
            self.this_sink = _sink
            # Get the full pad name (e.g., "sink_0", "sink_1", etc.)
            full_name = _sink.get_name()
            print(f"Full requested pad name: {full_name}")

            # Extract the integer index by splitting the string
            try:
                # Split the string "sink_N" by the underscore and take the second part
                index_str = full_name.split('_')[-1]
                self.sinks = int(index_str)
                
                print(f"Extracted unique index (%u): {self.sinks}")
            
            except ValueError:
                print(f"Error: Could not parse index from pad name: {full_name}")
            return _sink
        else:
            print("Error: Could not get a request pad.")

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_static_pad("src")

class Camera(GstElement):
    """
    V4L2 camera source. No sink pad (source element only).
    Set device: element.set_property("device", "/dev/video0")
    Set io-mode: element.set_property("io-mode", 4)  # DMABUF export
    """
    def __init__(self, name: str = None):
        super().__init__("v4l2src", name)

    @property
    def sink(self) -> None:
        return None

class Filter(GstElement):
    """
    Caps filter - enforces media format constraints.
    Pass format string in constructor: Filter("video/x-raw,width=1280,height=720")
    """
    def __init__(self, filter_str: str, name: str = None):
        super().__init__("capsfilter", name)
        caps = Gst.Caps.from_string(filter_str)
        self.element.set_property("caps", caps)

class GlColorConvert(GstElement):
    """
    Converts between color formats in OpenGL memory.
    Automatically negotiates format based on neighbor caps.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = None):
        super().__init__("glcolorconvert", name)

class GlColorscale(GstElement):
    """
    Scales video in OpenGL memory.
    Use with capsfilter to set target dimensions.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = None):
        super().__init__("glcolorscale", name)

class JpegEnc(GstElement):
    """
    JPEG encoder. Converts video/x-raw to image/jpeg.
    """
    def __init__(self, name: str = None):
        super().__init__("jpegenc", name)

class JpegDec(GstElement):
    """
    JPEG decoder. Converts image/jpeg to video/x-raw.
    Commonly used after MJPEG camera sources.
    """
    def __init__(self, name: str = None):
        super().__init__("jpegdec", name)

class EyePipe(GstElement):
    """
    Test video source with patterns. No sink pad (source element only).
    Set pattern: element.set_property("pattern", 0)  # 0-25 different patterns
    """
    def __init__(self, name: str = None):
        name = "eye" if not name else name
        super().__init__("videotestsrc", name)    
      
class GlUplPipe(GstElement):
    """
    Uploads video to OpenGL memory.
    Place after CPU elements, before GL processing elements.
    Converts video/x-raw to video/x-raw(memory:GLMemory).
    """
    def __init__(self, name: str = None):
        super().__init__("glupload", name)

class Tee(GstElement):
    """
    Splits pipeline into multiple branches.
    Use leg() to create new branch: branch = tee.leg()
    Each leg shares the same pipeline and can be appended independently.
    """
    def __init__(self, name: str = None):
        super().__init__("tee", name)

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_request_pad("src_%u")
    def link(self, sink) -> Gst.Element:
        return self.element.get_request_pad("src_%u").link(sink)
    def leg(self) -> Pipeline:
        leg = Pipeline(self)
        return leg

class Identity(GstElement):
    """
    Debug element - passes data unchanged.
    Call enable_caps_logging() to print format/dimensions during playback.
    Use descriptive names for identifying pipeline locations.
    """
    def __init__(self, name: str = None):
        super().__init__("identity", name)
        # Enable silent mode by default, prints can be enabled per instance
        self.element.set_property("silent", True)

    def enable_caps_logging(self):
        """Print caps (including width/height) when they change"""
        self.element.set_property("silent", False)
        self.element.set_property("signal-handoffs", True)
        # Connect to handoff signal to print caps
        def on_handoff(identity, _buffer):
            pad = identity.get_static_pad("src")
            caps = pad.get_current_caps()
            if caps:
                structure = caps.get_structure(0)
                width = structure.get_int("width")[1] if structure.has_field("width") else "?"
                height = structure.get_int("height")[1] if structure.has_field("height") else "?"
                logger.info(f"[{identity.get_name()}] Dimensions: {width}x{height}, Full caps: {caps.to_string()}")
        self.element.connect("handoff", on_handoff)
        return self

class XVidSink(GstElement):
    """
    X11 display sink using XImage.
    Accepts video/x-raw in system memory.
    Set force-aspect-ratio: element.set_property("force-aspect-ratio", False)
    """
    def __init__(self, name: str = None):
        super().__init__("ximagesink", name)

class GlVidSink(GstElement):
    """
    OpenGL display sink.
    Accepts video/x-raw(memory:GLMemory) for zero-copy display.
    Set force-aspect-ratio: element.set_property("force-aspect-ratio", False)
    """
    def __init__(self, name: str = None):
        super().__init__("glimagesinkelement", name)

class FileSink(GstElement):
    def __init__(self, name: str = None):
        super().__init__("filesink", name)

class UDPSink(GstElement):
    """
    UDP network sink for streaming.
    Set host: element.set_property("host", "192.168.0.2")
    Set port: element.set_property("port", 5000)
    Set sync: element.set_property("sync", False)  # For live streaming
    """
    def __init__(self, name: str = None):
        super().__init__("udpsink", name)

class Rock265Enc(GstElement):
    """
    Rockchip hardware H.265 encoder (mpph265enc).
    Efficient encoding on RK3588 devices.
    Raises RuntimeError if hardware encoder unavailable.
    """
    def __init__(self, name: str = None):
        super().__init__("mpph265enc", name)
        if not self.element:
            logger.error("Failed to create mpph265enc. Ensure GStreamer with GL support is installed.")
            raise RuntimeError("mpph265enc creation failed")


class GlShaderRotate90(GstElement):
    """
    Custom GL shader for 90-degree rotation in GPU memory.
    Pass clockwise=True/False in constructor.
    Swaps width/height - follow with capsfilter for rotated dimensions.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, clockwise: bool = True, name: str = None):
        super().__init__("glshader", name)

        # Fragment shader for rotation
        if clockwise:
            # 90° clockwise: (x,y) -> (1-y, x)
            transform = "1.0 - v_texcoord.y, v_texcoord.x"
        else:
            # 90° counter-clockwise: (x,y) -> (y, 1-x)
            transform = "v_texcoord.y, 1.0 - v_texcoord.x"

        fragment_shader = f"""
#version 100
#ifdef GL_ES
precision mediump float;
#endif
varying vec2 v_texcoord;
uniform sampler2D tex;

void main () {{
    vec2 rotated_coord = vec2({transform});
    gl_FragColor = texture2D(tex, rotated_coord);
}}
"""
        self.element.set_property("fragment", fragment_shader)

class GlDownload(GstElement):
    """
    Downloads video from OpenGL memory to system memory.
    Place before CPU elements that need video/x-raw in system memory.
    Converts video/x-raw(memory:GLMemory) to video/x-raw.
    """
    def __init__(self, name: str = None):
        super().__init__("gldownload", name)

class VideoConvert(GstElement):
    """
    Converts between video color spaces and formats in system memory.
    Automatically negotiates format. Use with capsfilter to force specific format.
    Essential between elements with incompatible formats.
    """
    def __init__(self, name: str = None):
        super().__init__("videoconvert", name)

class RtpH265Pay(GstElement):
    """
    RTP payloader for H.265/HEVC streams.
    Set pt: element.set_property("pt", 96)
    Set config-interval: element.set_property("config-interval", 1)  # Send SPS/PPS
    Set mtu: element.set_property("mtu", 1200)
    """
    def __init__(self, name: str = None):
        super().__init__("rtph265pay", name)
