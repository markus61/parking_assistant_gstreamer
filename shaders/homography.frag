#version 150

varying vec2 v_texcoord;
uniform sampler2D tex;

uniform bool clamp_uv = true; // 1 -> clamp into [0,1], 0 -> show outside color
uniform vec4 outside_color = vec4(0.0, 0.0, 1.0, 1.0);     // used only when clamp_uv == false
// Mat3 as 9 individual float uniforms (column-major order)
uniform float m00, m01, m02;
uniform float m10, m11, m12;
uniform float m20, m21, m22;

void main() {
    // Reconstruct mat3 from individual floats (column-major order)
    mat3 M = mat3(
        m00, m10, m20,
        m01, m11, m21,
        m02, m12, m22
    );

  // Perspective divide
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
