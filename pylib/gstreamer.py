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

class MxPipe(GstElement):

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

    def __init__(self, name: str = None):
        super().__init__("v4l2src", name)
        self.element.set_property("device", "/dev/video1")
        self.element.set_property("io-mode", 2)  # 0:MMAP, 1:USERPTR, 2:DMA-BUF

    @property
    def sink(self) -> None:
        return None

class Filter(GstElement):
    def __init__(self, filter_str: str, name: str = None):
        super().__init__("capsfilter", name)
        caps = Gst.Caps.from_string(filter_str)
        self.element.set_property("caps", caps)

class GlColorConvert(GstElement):
    def __init__(self, name: str = None):
        super().__init__("glcolorconvert", name)

class GlColorscale(GstElement):
    def __init__(self, name: str = None):
        super().__init__("glcolorscale", name)

class JpegDec(GstElement):
    def __init__(self, name: str = None):
        super().__init__("jpegdec", name)

class EyePipe(GstElement):
    def __init__(self, name: str = None):
        name = "eye" if not name else name
        super().__init__("videotestsrc", name)    
      
class GlUplPipe(GstElement):
    def __init__(self, name: str = None):
        super().__init__("glupload", name)

class Tee(GstElement):
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
    Debug element that passes data through and can print caps/timestamps.
    Use to inspect video dimensions at any point in the pipeline.
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
    def __init__(self, name: str = None):
        super().__init__("ximagesink", name)

class GlVidSink(GstElement):
    def __init__(self, name: str = None):
        super().__init__("glimagesinkelement", name)
        # Disable aspect ratio forcing to fill the window without black bars
        self.element.set_property("force-aspect-ratio", False)

class GlShaderRotate90(GstElement):
    """
    OpenGL shader that rotates video 90 degrees clockwise in GPU memory.
    Stays entirely in GL memory for maximum performance.
    """
    def __init__(self, clockwise: bool = True, name: str = None):
        super().__init__("glshader", name)

        # Fragment shader for rotation
        if clockwise:
            # 90° clockwise: (x,y) -> (1-y, x)
            fragment_shader = """
#version 100
#ifdef GL_ES
precision mediump float;
#endif
varying vec2 v_texcoord;
uniform sampler2D tex;

void main () {
    // Rotate 90 degrees clockwise
    vec2 rotated_coord = vec2(1.0 - v_texcoord.y, v_texcoord.x);
    gl_FragColor = texture2D(tex, rotated_coord);
}
"""
        else:
            # 90° counter-clockwise: (x,y) -> (y, 1-x)
            fragment_shader = """
#version 100
#ifdef GL_ES
precision mediump float;
#endif
varying vec2 v_texcoord;
uniform sampler2D tex;

void main () {
    // Rotate 90 degrees counter-clockwise
    vec2 rotated_coord = vec2(v_texcoord.y, 1.0 - v_texcoord.x);
    gl_FragColor = texture2D(tex, rotated_coord);
}
"""
        self.element.set_property("fragment", fragment_shader)
