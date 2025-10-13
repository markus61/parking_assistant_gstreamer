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

    @property
    def sink(self) -> Gst.Element:
        return self.element.get_request_pad("sink_%u")

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_static_pad("src")

class MyMixClass(MxPipe):

    def __init__(self, name: str = None):
        super().__init__(name)
        self.inputs = 0

    @property
    def sink(self) -> Gst.Element:
        sink = self.element.get_request_pad("sink_%u")
        sink.set_property("ypos", self.inputs * 720)
        self.inputs = self.inputs + 1
        return sink

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_static_pad("src")

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

class XVidSink(GstElement):
    def __init__(self, name: str = None):
        super().__init__("ximagesink", name)

class GlVidSink(GstElement):
    def __init__(self, name: str = None):
        super().__init__("glimagesinkelement", name)

def create_pipeline() -> Gst.Pipeline:
    xvidsink = XVidSink()
    glvidsink = GlVidSink()
    glcolorconvert = GlColorConvert()

    original = Pipeline()
    left_eye = EyePipe("left_eye")
    original.append(left_eye)
    f1 = Filter("video/x-raw,format=NV12,width=1280,height=720,framerate=15/1")
    original.append(f1)
    #original.append(xvidsink)

    glup = GlUplPipe()
    original.append(glup)
    original.append(glcolorconvert)

    tee = Tee()
    original.append(tee)
    mk = MyMixClass()
    original.append(mk)

    distorted = tee.leg()
    distorted.append(mk)

    original.append(glvidsink)

    return original.pipeline

