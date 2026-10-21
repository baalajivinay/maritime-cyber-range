shader_type spatial;
render_mode cull_disabled, specular_schlick_ggx;

// Wave field driven by the SITE's real sea state (fed from the relay):
//   hs = significant wave height, tp = peak period, dir_deg = dominant bearing.
uniform float time = 0.0;
uniform float hs = 1.2;
uniform float tp = 7.0;
uniform float dir_deg = 160.0;
uniform vec3 deep_color : source_color = vec3(0.008, 0.07, 0.13);
uniform vec3 shallow_color : source_color = vec3(0.03, 0.26, 0.36);
uniform vec3 foam_color : source_color = vec3(0.90, 0.95, 0.97);

const float G = 9.81;

// four Gerstner components spread around the dominant direction
void gerstner(vec2 p, out float height, out vec3 normal) {
    height = 0.0;
    vec3 n = vec3(0.0, 1.0, 0.0);
    float base = radians(dir_deg);
    float fracs[4] = {1.0, 0.45, 0.28, 0.16};
    float dang[4]  = {0.0, 0.5, -0.7, 1.1};
    float amp_scale = max(0.15, hs) * 0.5;
    for (int i = 0; i < 4; i++) {
        float T = max(tp * (i == 0 ? 1.0 : (i == 1 ? 0.7 : (i == 2 ? 0.45 : 0.3))), 1.4);
        float w = 2.0 * PI / T;
        float L = G * T * T / (2.0 * PI);
        float k = 2.0 * PI / L;
        float ang = base + dang[i];
        vec2 d = vec2(cos(ang), sin(ang));
        float a = amp_scale * fracs[i];
        float steep = 0.55 * fracs[i];
        float ph = k * dot(d, p) - w * time + float(i) * 1.7;
        float c = cos(ph);
        float s = sin(ph);
        height += a * s;
        n.x -= d.x * k * a * c;
        n.z -= d.y * k * a * c;
    }
    normal = normalize(n);
}

varying float v_height;

void vertex() {
    vec2 p = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
    float h;
    vec3 n;
    gerstner(p, h, n);
    VERTEX.y += h;
    NORMAL = n;
    v_height = h;
}

void fragment() {
    float crest = smoothstep(0.55 * max(0.2, hs), 1.05 * max(0.2, hs), v_height);
    float k = clamp((v_height + hs) / (2.0 * hs + 0.001), 0.0, 1.0);
    vec3 water = mix(deep_color, shallow_color, k);
    ALBEDO = mix(water, foam_color, crest * 0.6);
    METALLIC = 0.0;
    ROUGHNESS = mix(0.04, 0.35, crest);   // glassy water, rougher foam
    SPECULAR = 0.6;
    // subtle sub-surface tint
    EMISSION = shallow_color * 0.04;
}
