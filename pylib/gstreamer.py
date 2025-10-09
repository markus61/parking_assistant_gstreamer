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
        name = "" if not name else name
        self.element = Gst.ElementFactory.make(element, name)
        self._name = name

    @property
    def name(self) -> str:
        return self.element.get_name()
    @property
    def src(self) -> Gst.Element:
        return self.element.get_static_pad("src")
    
    @property
    def sink(self) -> Gst.Element:
        return self.element.get_static_pad("sink")

    def link(self, sink) -> Gst.Element:            
        return self.src.link(sink)


class Pipeline():
    def __init__(self, name: str = "", element: GstElement = None):
        name = "tube" if not name else name
        self.pipeline = Gst.Pipeline.new(name) or None
        self.tail = element or None
        if element:
            self.pipeline.add(element.element)

    @property
    def gst_pipeline(self) -> Gst.Pipeline:
        return self.pipeline

    def append(self, element: GstElement):
        self.pipeline.add(element.element)
        type_name = element.element.__gtype__.name

        if self.tail is None:
            self.tail = element
            return self

        if isinstance(element.sink, list):
            self.tail.src.link(element.sink.pop())
        else:
            self.tail.src.link(element.sink)
        self.tail = element
        return self


class Filter(GstElement):
    def __init__(self, filter_str: str, name: str = ""):
        super().__init__("capsfilter", name)
        caps = Gst.Caps.from_string(filter_str)
        self.element.set_property("caps", caps)

class GlColorscale(GstElement):
    def __init__(self, name: str = ""):
        super().__init__("glcolorscale", name)

class EyePipe(GstElement):
    def __init__(self, name: str = ""):
        name = "eye" if not name else name
        super().__init__("videotestsrc", name)    
      
class GlUplPipe(GstElement):
    def __init__(self, name: str = ""):
        super().__init__("glupload", name)

class Tee(GstElement):
    def __init__(self, name = ""):
        super().__init__("tee", name)

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_request_pad("src_%u")
    def link(self, sink) -> Gst.Element:
        return self.element.get_request_pad("src_%u").link(sink)

class MxPipe(GstElement):

    def __init__(self, name: str = ""):
        super().__init__("glvideomixer", name)

    @property
    def sink(self) -> Gst.Element:
        return self.element.get_request_pad("sink_%u")

    @property
    def src(self) -> Gst.Pad:
        return self.element.get_static_pad("src")

def create_glmixer(name: str) -> Gst.Element:
    name = "glmixer" if not name else name
    glmixer = Gst.ElementFactory.make("glvideomixer", name)
    left = glmixer.get_request_pad("sink_%u")
    right = glmixer.get_request_pad("sink_%u")
    return glmixer, left, right 

def create_tee(name: str) -> Gst.Element:
    name = "t" if not name else name
    t = Gst.ElementFactory.make("tee", name)
    left = t.get_request_pad("src_%u")
    right = t.get_request_pad("src_%u")
    return t, left, right

def create_filter(name: str) -> Gst.Element:
    capsfilter = Gst.ElementFactory.make("capsfilter", name)
    caps = Gst.Caps.from_string("video/x-raw,format=NV12,width=1280,height=720,framerate=15/1")
    capsfilter.set_property("caps", caps)
    return capsfilter

def create_source(name: str) -> Gst.Element:
    source = Gst.ElementFactory.make("videotestsrc", name)
    source.set_property("pattern",0)
    return source

def create_sink() -> Gst.Element:
    return Gst.ElementFactory.make("autovideosink", "sink")

def create_compositor() -> Gst.Element:
    comp = Gst.ElementFactory.make("compositor", "comp")
    left = comp.get_request_pad("sink_%u")
    right = comp.get_request_pad("sink_%u")
    right.set_property("xpos", 1280)
    return comp, left, right

def create_pipeline() -> Gst.Pipeline:
    pipeline = Pipeline()
    left_eye = EyePipe("left_eye")
    pipeline.append(left_eye)
    f1 = Filter("video/x-raw,format=NV12,width=1280,height=720,framerate=15/1")
    pipeline.append(f1)
    glup = GlUplPipe()
    pipeline.append(glup)
    f2=Filter("video/x-raw(memory:GLMemory),format=RGBA,width=1280,height=720,framerate=15/1")
    pipeline.append(f2)
    glcolor = GlColorscale()
    pipeline.append(glcolor)
    tee = Tee()
    pipeline.append(tee)
    mk = MxPipe()
    pipeline.append(mk)

    return pipeline.pipeline

def walk_pattern(pipeline: Gst.Pipeline):
    left_eye = pipeline.get_by_name("left_eye")
    right_eye = pipeline.get_by_name("right_eye")
    pattern = int(left_eye.props.pattern)
    pattern = pattern + 1
    if pattern == 23:
        # Send EOS to stop the pipeline gracefully
        pipeline.send_event(Gst.Event.new_eos())
        return False
    left_eye.set_property("pattern", pattern)
    right_eye.set_property("pattern", pattern)
    print(f"Pattern {pattern}")
    return True


