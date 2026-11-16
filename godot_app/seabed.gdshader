shader_type spatial;
render_mode cull_back, specular_schlick_ggx;

// World-space acoustic bathymetric seafloor shader
// Renders dynamic contours and acoustic survey grid based on TRUE world coordinates
uniform vec3 sand_color : source_color = vec3(0.20, 0.28, 0.24);
uniform vec3 rock_color : source_color = vec3(0.09, 0.15, 0.13);
uniform vec3 grid_color : source_color = vec3(0.18, 0.48, 0.38);

varying vec2 world_pos;

void vertex() {
    world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
    // Multi-frequency seafloor sediment contours
    float n1 = sin(world_pos.x * 0.14) * cos(world_pos.y * 0.14);
    float n2 = sin(world_pos.x * 0.035 + world_pos.y * 0.045);
    float n3 = cos(world_pos.x * 0.01 - world_pos.y * 0.015);
    
    // 20m high-contrast bathymetric acoustic survey grid
    float gx = smoothstep(0.95, 1.0, fract(world_pos.x / 20.0));
    float gz = smoothstep(0.95, 1.0, fract(world_pos.y / 20.0));
    float grid = max(gx, gz);
    
    // Micro ripple texture (simulates sonar scan texture)
    float micro = sin(world_pos.x * 1.5 + world_pos.y * 1.2) * 0.08;
    
    vec3 col = mix(rock_color, sand_color, clamp(0.5 + 0.4 * (n1 * 0.6 + n2 * 0.4) + micro, 0.0, 1.0));
    col = mix(col, grid_color, grid * 0.55);
    
    ALBEDO = col;
    ROUGHNESS = 0.88;
    SPECULAR = 0.25;
}
