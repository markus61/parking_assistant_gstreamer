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
    pipeline = Gst.Pipeline.new("test-pipeline")
    left_caps = create_filter("left_caps")
    right_caps = create_filter("right_caps")
    left_eye = create_source("left_eye")
    right_eye = create_source("right_eye")
    comp, left, right = create_compositor()
    sink = create_sink()

    pipeline.add(left_eye)
    pipeline.add(left_caps)
    pipeline.add(right_eye)
    pipeline.add(right_caps)
    pipeline.add(sink)
    pipeline.add(comp)

    # plumbing
    left_eye.get_static_pad("src").link(left_caps.get_static_pad("sink"))
    left_caps.get_static_pad("src").link(left)
    right_eye.get_static_pad("src").link(right_caps.get_static_pad("sink"))
    right_caps.get_static_pad("src").link(right)
    comp.link(sink)
    GLib.timeout_add(1000, walk_pattern, pipeline)
    return pipeline

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


