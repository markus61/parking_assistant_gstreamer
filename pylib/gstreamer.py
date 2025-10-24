import sys
import gi
import logging
import numpy as np

gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gst, GLib, GObject  # type: ignore
from . import camera_config

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

# Initialize GStreamer
Gst.init(sys.argv[1:])

class Element():
    """Base wrapper for GStreamer elements. Provides name, src/sink pads, and linking."""
    def __init__(self, element: str, name: str):
        self.element:Gst.Element = Gst.ElementFactory.make(element, name)
        # assert self.element is not None, f"Failed to create GStreamer element: {element}"
        self._name: str | None = self.element.get_name() if self.element else ""
        self.pipeline = None

    @property
    def name(self) -> str | None:
        return self._name
    @property
    def src(self) -> Gst.Pad | None:
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
    def __init__(self, element: Element = None, name: str = None ):
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

    def add(self, element: Element):
        self.pipeline.add(element.element)
        element.pipeline = self.pipeline
        self.tail = element
        return self

    def link(self, element: Element):
        if not element.pipeline:
            raise RuntimeError("Element must be added to a pipeline before linking.")
        
        # Link tail to new element
        link_result = self.tail.src.link(element.sink)
        if link_result != Gst.PadLinkReturn.OK:
            logger.error(f"Failed to link {self.tail.name} -> {element.name}: {link_result}")
            raise RuntimeError(f"Pad linking failed: {link_result}")

        logger.info(f"Linked {self.tail.name} -> {element.name}")
        self.tail = element
        return self

    def append(self, element: Element):
        """
        Appends an element to the pipeline, linking it to the tail if it exists.
        If the pipeline is empty, the element is added to the pipeline.
        """
        if self.tail is None:
            return self.add(element)
        tail = self.tail
        self.add(element)
        self.tail = tail
        return self.link(element)

    def cleanup(self):
        """Sets the pipeline to NULL state to stop it and free resources."""
        if self.pipeline:
            print("Stopping pipeline and releasing resources...")
            
            # 1. Set the state to NULL
            # This is the equivalent of "removing" the pipeline.
            self.pipeline.set_state(Gst.State.NULL)
            
            print("Pipeline stopped.")

class MxPipe(Element):
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

class Camera(Element):
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

class Filter(Element):
    """
    Caps filter - enforces media format constraints.
    Pass format string in constructor: Filter("video/x-raw,width=1280,height=720")
    """
    def __init__(self, filter_str: str, name: str = None):
        super().__init__("capsfilter", name)
        caps = Gst.Caps.from_string(filter_str)
        self.element.set_property("caps", caps)

class GlColorConvert(Element):
    """
    Converts between color formats in OpenGL memory.
    Automatically negotiates format based on neighbor caps.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = None):
        super().__init__("glcolorconvert", name)

class GlColorscale(Element):
    """
    Scales video in OpenGL memory.
    Use with capsfilter to set target dimensions.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = None):
        super().__init__("glcolorscale", name)

class JpegEnc(Element):
    """
    JPEG encoder. Converts video/x-raw to image/jpeg.
    """
    def __init__(self, name: str = None):
        super().__init__("jpegenc", name)

class JpegDec(Element):
    """
    JPEG decoder. Converts image/jpeg to video/x-raw.
    Commonly used after MJPEG camera sources.
    """
    def __init__(self, name: str = None):
        super().__init__("jpegdec", name)

class TestVidSrc(Element):
    """
    Test video source with patterns. No sink pad (source element only).
    Set pattern: element.set_property("pattern", 0)  # 0-25 different patterns
    """
    def __init__(self, name: str = None):
        super().__init__("videotestsrc", name)    
      
class GlUplPipe(Element):
    """
    Uploads video to OpenGL memory.
    Place after CPU elements, before GL processing elements.
    Converts video/x-raw to video/x-raw(memory:GLMemory).
    """
    def __init__(self, name: str = None):
        super().__init__("glupload", name)

class Tee(Element):
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

class Identity(Element):
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

class XVidSink(Element):
    """
    X11 display sink using XImage.
    Accepts video/x-raw in system memory.
    Set force-aspect-ratio: element.set_property("force-aspect-ratio", False)
    """
    def __init__(self, name: str = None):
        super().__init__("ximagesink", name)

class GlVidSink(Element):
    """
    OpenGL display sink.
    Accepts video/x-raw(memory:GLMemory) for zero-copy display.
    Set force-aspect-ratio: element.set_property("force-aspect-ratio", False)
    """
    def __init__(self, name: str = None):
        super().__init__("glimagesinkelement", name)

class FileSink(Element):
    def __init__(self, name: str = None):
        super().__init__("filesink", name)

class UDPSink(Element):
    """
    UDP network sink for streaming.
    Set host: element.set_property("host", "192.168.0.2")
    Set port: element.set_property("port", 5000)
    Set sync: element.set_property("sync", False)  # For live streaming
    """
    def __init__(self, name: str = None):
        super().__init__("udpsink", name)

class Rock265Enc(Element):
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


class GlShaderRotate90(Element):
    """
    Custom GL shader for 90-degree rotation in GPU memory.
    Pass clockwise=True/False in constructor.
    Swaps width/height - follow with capsfilter for rotated dimensions.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, clockwise: bool = True, name: str = None):
        super().__init__("glshader", name)

        # Fragment shader for rotation with optional distortion correction
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
    // apply rotation
    vec2 uv = v_texcoord;
    vec2 rotated_coord = vec2({transform});

    // Sample with bounds checking
    if (uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0) {{
        gl_FragColor = texture2D(tex, rotated_coord);
    }} else {{
        gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
    }}
}}
"""
        self.element.set_property("fragment", fragment_shader)

class GlShaderHomography2(Element):
    def __init__(self, name: str = "", matrix = []):
        super().__init__("glshader", name)

        shader_vert = r"""
#version 300 es
precision mediump float;
in vec4 a_position;
in vec2 a_texcoord;
out vec2 v_texcoord;
void main() {
    gl_Position = a_position;
    v_texcoord = a_texcoord;
}
"""

        shader_frag = r"""
#version 300 es
precision mediump float;
uniform sampler2D tex;
uniform mat3 H;
in vec2 v_texcoord;
out vec4 fragColor;
void main() {
    vec3 uvw = vec3(v_texcoord, 1.0);
    vec3 warped = H * uvw;
    float w = warped.z;
    vec2 new_uv = (w != 0.0) ? (warped.xy / w) : vec2(0.0);
    new_uv = clamp(new_uv, 0.0, 1.0);
    fragColor = texture(tex, new_uv);
}
"""
        # === IMPORTANT: column-major for GLSL ===
        # GLSL expects column-major order; glshader uses that convention.
        # If you build H row-major (NumPy default), pass H.T.flatten().
        H_vals = matrix.T.flatten()

        # (Sampler 'tex' is bound for you; no need to set unless you changed names.)

        self.element.set_property("vertex", shader_vert)
        self.element.set_property("fragment", shader_frag)
        self.element.set_property("uniforms", "H: " + " ".join(str(x) for x in H_vals))

class GlShaderWarpPerspective(Element):
    """
    Applies 2D perspective transformation using homography matrix.
    Corrects keystone distortion from camera tilt angles.
    Homography transforms perspective view to orthographic projection.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = "", matrix: list=[]):
        super().__init__("glshader", name)

        fragment_shader = f"""
#version 330 core

uniform sampler2D u_texture;
uniform mat3 u_homography;  // Column-major homography matrix

in vec2 v_texcoord;
out vec4 fragColor;

void main() {{
    // Homography matrix (3x3) - perspective transformation in pixel space
    u_homography = mat3(
        // GLSL's mat3 constructor is column-major. We must transpose the row-major matrix.
        {matrix[0]}, {matrix[3]}, {matrix[6]},  // Column 1
        {matrix[1]}, {matrix[4]}, {matrix[7]},  // Column 2
        {matrix[2]}, {matrix[5]}, {matrix[8]}   // Column 3
    );

    // Convert texture coordinates to pixel coordinates
    // OpenGL texture coords are [0,1], need to match image coordinates
    vec2 pixel_coord = v_texcoord;
    
    // Apply homography transformation (forward mapping)
    // For warpPerspective, we need INVERSE mapping:
    // Find where this output pixel came from in the source image
    
    vec3 homogeneous_coord = vec3(pixel_coord, 1.0);
    vec3 transformed = u_homography * homogeneous_coord;
    
    // Perspective divide (convert from homogeneous to Cartesian)
    vec2 source_coord = transformed.xy / transformed.z;
    
    // Check if source coordinate is within valid range [0, 1]
    if (source_coord.x < 0.0 || source_coord.x > 1.0 ||
        source_coord.y < 0.0 || source_coord.y > 1.0) {{
        // Outside source image - return black
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
    }} else {{
        // Sample from source texture
        fragColor = texture(u_texture, source_coord);
    }}
}}
        
"""

class GlShaderHomography(Element):
    """
    Applies 2D perspective transformation using homography matrix.
    Corrects keystone distortion from camera tilt angles.
    Homography transforms perspective view to orthographic projection.
    Gets camera configuration internally and converts shader to use pixel coordinates.
    Requires video/x-raw(memory:GLMemory) input.
    """
    def __init__(self, name: str = "", matrix: list=[]):
        super().__init__("glshader", name)

        # Get camera configuration and compute homography matrix
        config = camera_config.CameraConfig()

        # Get image dimensions
        width = config.resolution[0]
        height = config.resolution[1]

        # Debug: print homography matrix and config
        logger.info(f"GlShaderHomography: resolution={width}x{height}")
        logger.info(f"GlShaderHomography: tilt_angle={config.tilt_angle}°")
        logger.info(f"GlShaderHomography: distance={config.distance_to_object_plane}m")
        logger.info(f"GlShaderHomography matrix:\n  [{matrix[0]:.6f}, {matrix[1]:.6f}, {matrix[2]:.6f}]\n  [{matrix[3]:.6f}, {matrix[4]:.6f}, {matrix[5]:.6f}]\n  [{matrix[6]:.6f}, {matrix[7]:.6f}, {matrix[8]:.6f}]")

        fragment_shader = f"""
#version 100
#ifdef GL_ES
precision highp float;
#endif
varying vec2 v_texcoord;
uniform sampler2D tex;

void main () {{
    vec2 uv = v_texcoord;

    // Convert texture coordinates [0,1] to pixel coordinates [0,width]x[0,height]
    vec2 pixel_coord = uv * vec2({width}.0, {height}.0);

    // Homography matrix (3x3) - perspective transformation in pixel space
    mat3 H = mat3(
        // GLSL's mat3 constructor is column-major. We must transpose the row-major matrix.
        {matrix[0]}, {matrix[3]}, {matrix[6]},  // Column 1
        {matrix[1]}, {matrix[4]}, {matrix[7]},  // Column 2
        {matrix[2]}, {matrix[5]}, {matrix[8]}   // Column 3
    );

    // Apply homography: p' = H * p (homogeneous coordinates in pixel space)
    vec3 pixel_homogeneous = vec3(pixel_coord.x, pixel_coord.y, 1.0);
    vec3 transformed = H * pixel_homogeneous;

    // Perspective divide to convert back to 2D pixel coordinates
    vec2 corrected_pixel = transformed.xy / transformed.z;

    // Convert back to texture coordinates [0,1]
    vec2 corrected_uv = corrected_pixel / vec2({width}.0, {height}.0);

    // Sample texture with corrected coordinates
    if (corrected_uv.x >= 0.0 && corrected_uv.x <= 1.0 &&
        corrected_uv.y >= 0.0 && corrected_uv.y <= 1.0) {{
        gl_FragColor = texture2D(tex, corrected_uv);
    }} else {{
        // Black for out-of-bounds areas
        gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
    }}
}}
"""
        self.element.set_property("fragment", fragment_shader)

class GlDownload(Element):
    """
    Downloads video from OpenGL memory to system memory.
    Place before CPU elements that need video/x-raw in system memory.
    Converts video/x-raw(memory:GLMemory) to video/x-raw.
    """
    def __init__(self, name: str = None):
        super().__init__("gldownload", name)

class VideoConvert(Element):
    """
    Converts between video color spaces and formats in system memory.
    Automatically negotiates format. Use with capsfilter to force specific format.
    Essential between elements with incompatible formats.
    """
    def __init__(self, name: str = None):
        super().__init__("videoconvert", name)

class RtpH265Pay(Element):
    """
    RTP payloader for H.265/HEVC streams.
    Set pt: element.set_property("pt", 96)
    Set config-interval: element.set_property("config-interval", 1)  # Send SPS/PPS
    Set mtu: element.set_property("mtu", 1200)
    """
    def __init__(self, name: str = None):
        super().__init__("rtph265pay", name)
