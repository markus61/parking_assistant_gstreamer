#version 150

// Input attributes from GStreamer
in vec4 a_position;
in vec2 a_texcoord;

// Output to fragment shader
out vec2 v_texcoord;

void main() {
    gl_Position = a_position;
    v_texcoord = a_texcoord;
}
