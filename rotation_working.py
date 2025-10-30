#!/usr/bin/env python

import math
import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstGL', '1.0')

from gi.repository import GObject, Gst, GLib

# --- GLSL Shader Code ---

# A simple passthrough vertex shader
VERTEX_SRC = """
#version 150
in vec4 a_position;
in vec2 a_texcoord;
out vec2 v_texcoord;

void main() {
    gl_Position = a_position;
    v_texcoord = a_texcoord;
}
"""

# Fragment shader that reconstructs mat3 from 9 individual float uniforms
FRAGMENT_SRC = """
#version 150
in vec2 v_texcoord;
out vec4 out_color;

uniform sampler2D tex;
// Mat3 as 9 individual float uniforms (column-major order)
uniform float m00, m01, m02;
uniform float m10, m11, m12;
uniform float m20, m21, m22;

void main() {
    // Reconstruct mat3 from individual floats (column-major order)
    mat3 matrix = mat3(
        m00, m01, m02,
        m10, m11, m12,
        m20, m21, m22
    );

    // Center coordinates
    vec2 center = vec2(0.5, 0.5);
    vec2 coords = v_texcoord - center;

    // Apply the matrix
    vec3 new_coords = matrix * vec3(coords, 1.0);

    // Un-center and sample
    out_color = texture(tex, new_coords.xy + center);
}
"""
def create_mat3_uniform_structure(matrix_data: list) -> Gst.Structure:
    """
    Creates a Gst.Structure for a mat3 uniform for the glshader element.

    The glshader element only supports individual float/int values and Graphene types.
    For a mat3, we pass it as 9 individual float uniforms: m00-m22 (column-major).

    Args:
        matrix_data: List of 9 floats in column-major order

    Returns:
        GstStructure with 9 float fields (m00, m01, m02, m10, m11, m12, m20, m21, m22)
    """
    if len(matrix_data) != 9:
        raise ValueError(f"matrix_data must contain exactly 9 floats, got {len(matrix_data)}")

    # Create the uniforms structure with 9 individual float fields
    uniforms = Gst.Structure.new_empty("uniforms")

    # Set each matrix element as an individual float uniform (column-major order)
    uniform_names = ["m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22"]
    for name, val in zip(uniform_names, matrix_data):
        uniforms.set_value(name, GObject.Value(GObject.TYPE_FLOAT, float(val)))

    return uniforms

def main():
    Gst.init(sys.argv)

    # --- 1. Build the Pipeline ---
    print("Building pipeline...")
    pipeline = Gst.Pipeline.new()

    # Create elements
    src = Gst.ElementFactory.make("videotestsrc")
    src.set_property("is-live", True)
    src.set_property("pattern", 0) # Start with SMPTE color bars
    glupload = Gst.ElementFactory.make("glupload")

    # Use 'glshader' instead of 'gltransformation'
    shader_elem = Gst.ElementFactory.make("glshader")
    if not shader_elem:
        print("Missing GStreamer element: glshader")
        return

    sink = Gst.ElementFactory.make("glimagesink")

    # --- 2. Define Shader and Uniforms in a Gst.Structure ---
    # For glshader, we set the vertex and fragment shaders directly,
    # and then provide the uniforms in a separate Gst.Structure.
    shader_elem.set_property("vertex", VERTEX_SRC)
    shader_elem.set_property("fragment", FRAGMENT_SRC)

    # Create the Gst.Structure for the 'uniforms' property
    angle = 3.14159 / 4.0  # 45 degrees
    c = math.cos(angle)
    s = math.sin(angle)
    matrix_data = [c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0]

    # Create the uniform structure programmatically.
    # Pass the mat3 as 9 individual float uniforms (m00-m22).
    uniforms = create_mat3_uniform_structure(matrix_data)
    shader_elem.set_property("uniforms", uniforms)

    # Add and link
    pipeline.add(src)
    pipeline.add(glupload)
    pipeline.add(shader_elem)
    pipeline.add(sink)

    src.link(glupload)
    glupload.link(shader_elem)
    shader_elem.link(sink)
    
    # --- Bus message handling (to catch errors) ---
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(bus, msg):
        t = msg.type
        if t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print(f"ERROR: {err}, DEBUG: {dbg}")
            loop.quit()
        elif t == Gst.MessageType.EOS:
            print("End-Of-Stream reached.")
            loop.quit()
        return True # Continue watching for messages

    bus.connect("message", on_message)

    # --- Dynamic Uniform Update (Visual Verification) ---
    start_time = GLib.get_monotonic_time()

    def update_shader_uniforms():
        nonlocal start_time
        current_time = GLib.get_monotonic_time()
        elapsed_seconds = (current_time - start_time) / 1e6

        # Rotate 30 degrees per second
        angle = elapsed_seconds * math.radians(30)

        c = math.cos(angle)
        s = math.sin(angle)

        # Rotation matrix (column-major for GLSL mat3)
        matrix_data = [c, s, 0.0,  # Column 0
                       -s, c, 0.0, # Column 1
                       0.0, 0.0, 1.0] # Column 2

        uniforms_update = create_mat3_uniform_structure(matrix_data)
        shader_elem.set_property("uniforms", uniforms_update)
        return True # Keep calling this function

    # Call update_shader_uniforms approximately 60 times per second (~16ms interval)
    GLib.timeout_add(16, update_shader_uniforms)

    # --- 3. Run the Pipeline ---
    # Run
    print("Running pipeline... (Press Ctrl+C to stop)")
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("Stopping pipeline.")

    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    main()