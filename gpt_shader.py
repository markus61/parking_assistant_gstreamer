#!/usr/bin/env python3
import math
import numpy as np
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstGL', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

VERT_100 = r"""#version 100
attribute vec4 a_position;
attribute vec2 a_texcoord;
varying   vec2 v_texcoord;
void main() {
  gl_Position = a_position;
  v_texcoord  = a_texcoord;
}
"""

FRAG_100 = r"""#version 100
precision mediump float;
varying vec2 v_texcoord;
uniform sampler2D tex;
uniform mat3 M;
uniform bool clamp_uv;
uniform vec4 outside_color;
void main() {
  vec3 uvw = M * vec3(v_texcoord, 1.0);
  float w = (abs(uvw.z) > 1e-8) ? uvw.z : 1e-8;
  vec2  uv = uvw.xy / w;
  if (clamp_uv) {
    uv = clamp(uv, 0.0, 1.0);
    gl_FragColor = texture2D(tex, uv);
  } else {
    bool oob = any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)));
    gl_FragColor = oob ? outside_color : texture2D(tex, uv);
  }
}
"""

# --- Helpers -----------------------------------------------------------------

def uniforms_from_mat3(M: np.ndarray):
    """
    Build a Gst.Structure for glshader 'uniforms' from a 3×3 numpy array.
    OpenGL wants column-major; NumPy is row-major → send M.T.flatten().
    Uses robust string serialization to avoid GI array type quirks.
    """
    M_flat = M.T.flatten()  # column-major order
    vals = ", ".join(f"{x:.9f}" for x in M_flat)
    s, _ = Gst.Structure.from_string(f"uniforms, M=(float)<{vals}>, clamp_uv=(boolean)true, outside_color=(float)<0.0, 0.0, 0.0, 1.0>")
    return s

def rotate_about_center(theta_rad: float):
    """
    Build a 3×3 homography that rotates UV around the image center (0.5, 0.5).
    Works for any theta (affine subset; third row is [0,0,1]).
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    R = np.array([[ c, -s, 0.0],
                  [ s,  c, 0.0],
                  [0.0, 0.0, 1.0]], dtype=np.float32)
    T_to   = np.array([[1, 0, -0.5],
                       [0, 1, -0.5],
                       [0, 0,  1.0]], dtype=np.float32)
    T_back = np.array([[1, 0,  0.5],
                       [0, 1,  0.5],
                       [0, 0,  1.0]], dtype=np.float32)
    return (T_back @ R @ T_to).astype(np.float32)

# --- Pipeline ----------------------------------------------------------------
frag_esc = FRAG_100.replace('"', '\\"')
vert_esc = VERT_100.replace('"', '\\"')

pipeline = Gst.parse_launch(
    "videotestsrc is-live=true pattern=smpte ! "
    "video/x-raw,format=RGBA,width=1280,height=720,framerate=60/1 ! "
    "glupload ! "
    f'glshader name=warp vertex="{vert_esc}" fragment="{frag_esc}" ! '
    "glimagesink sync=false"
)

shader = pipeline.get_by_name("warp")
test_src = pipeline.get_by_name("videotestsrc0")

# Set an initial matrix (identity)
M0 = np.eye(3, dtype=np.float32)
shader.set_property("uniforms", uniforms_from_mat3(M0))
test_src.set_property("pattern", 0)
# Bus logging (optional but handy)
bus = pipeline.get_bus()
assert bus is not None
bus.add_signal_watch()
def on_msg(bus, msg):
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg)
        loop.quit()
    elif t == Gst.MessageType.EOS:
        loop.quit()
bus.connect("message", on_msg)

# Start pipeline
pipeline.set_state(Gst.State.PLAYING)

# Animate: update M ~60fps
loop = GLib.MainLoop()
t0 = GLib.get_monotonic_time()

def tick_1():
    pattern = test_src.get_property("pattern") +1
    test_src.set_property("pattern", pattern)
 
def tick():
    # elapsed seconds
    t_now = GLib.get_monotonic_time()
    t = (t_now - t0) / 1e6

    # Example: slow rotation + tiny breathing scale to prove it's live
    theta = 0.3 * math.sin(t * 0.7)            # radians
    scale = 1.0 + 0.05 * math.sin(t * 0.9)     #  ±5%
    R = rotate_about_center(theta)
    S = np.array([[scale, 0, 0],
                  [0, scale, 0],
                  [0, 0, 1]], dtype=np.float32)
    M = (S @ R).astype(np.float32)

    try:
        shader.set_property("uniforms", uniforms_from_mat3(M))
    except Exception as e:
        # If the GL context isn't ready yet, just try again next tick
        print("uniform update warning:", e)

    # ~60 Hz
    return True

GLib.timeout_add(1000, tick_1)  # 16ms ≈ 60 fps

try:
    loop.run()
except KeyboardInterrupt:
    pass
finally:
    pipeline.set_state(Gst.State.NULL)
