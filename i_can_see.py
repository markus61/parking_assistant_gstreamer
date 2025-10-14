#!/usr/bin/env python3

import sys
import logging
import gi
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib  # type: ignore

logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

from pylib import create_pipeline

pipeline = create_pipeline()
# Modify the source's properties
##source.props.pattern = 0
# Can alternatively be done using `source.set_property("pattern",0)`
# or using `Gst.util_set_object_arg(source, "pattern", 0)`

# Start playing
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    logger.error("Unable to set the pipeline to playing state.")
    sys.exit(1)

# Wait for EOS or error using a main loop
def on_message(bus, message, loop):
    if message.type == Gst.MessageType.ERROR:
        err, debug_info = message.parse_error()
        logger.error(f"Error received from element {message.src.get_name()}: {err.message}")
        logger.error(f"Debugging information: {debug_info if debug_info else 'none'}")
        loop.quit()
    elif message.type == Gst.MessageType.EOS:
        logger.info("End-Of-Stream reached.")
        loop.quit()

loop = GLib.MainLoop()
bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message, loop)

loop.run()

pipeline.set_state(Gst.State.NULL)