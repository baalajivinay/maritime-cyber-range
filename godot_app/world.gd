extends Node3D
# Maritime Cyber Range -- Godot 4 front-end.
# Renders the ocean + vehicle and drives the HUD. All physics/attacks live in
# the headless ArduPilot SITL; tools/godot_relay.py bridges MAVLink <-> this app
# over JSON/UDP (telemetry in on 14650, commands out on 14651).

const TELE_PORT := 14650
const CMD_ADDR := "127.0.0.1"
const CMD_PORT := 14651
const DEG_M := 111320.0

var net: PacketPeerUDP
var cmd: PacketPeerUDP
var tele := {}
var home := Vector2(9.9, 76.2)
var domain := "surface"
var connected := false
var booting := false

var ocean_mat: ShaderMaterial
var env: WorldEnvironment
var sun: DirectionalLight3D
var vehicle: Node3D
var vkind := ""
var cam: Camera3D
var cam_f := 0.0
var cam_target := 0.0
var heading := 0.0
var dest_rel = null          # Vector2 east,north relative to vehicle
var dest_world = null         # Vector3 world position of the waypoint marker
var dest_marker: MeshInstance3D
var setting_dest := false
var seabed: MeshInstance3D
var snow: GPUParticles3D

var hud: Control
var labels := {}
var menu: Control
var sel_site := 0
var sel_twin := 0
var active_attack := ""

const SITES := ["kochi", "mumbai", "visakhapatnam"]
const TWINS := [
	{"id": "interceptor_usv", "dom": "surface", "name": "Fast Interceptor USV"},
	{"id": "survey_usv", "dom": "surface", "name": "Coastal Survey USV"},
	{"id": "maya_auv", "dom": "underwater", "name": "Maya AUV"},
	{"id": "auv150", "dom": "underwater", "name": "AUV-150"},
]

func _ready():
	_build_world()
	_build_hud()
	_build_menu()
	net = PacketPeerUDP.new()
	net.bind(TELE_PORT)
	cmd = PacketPeerUDP.new()
	cmd.set_dest_address(CMD_ADDR, CMD_PORT)
	if OS.has_environment("MCR_SHOT"):
		_preview_shot()

func _preview_shot():
	var veh := OS.get_environment("MCR_SHOT_VEH") if OS.has_environment("MCR_SHOT_VEH") else "interceptor_usv"
	domain = "underwater" if veh in ["maya_auv", "auv150"] else "surface"
	_build_vehicle(veh)
	_apply_domain_visuals()
	menu.visible = false
	connected = true
	tele = {"hdg": 35.0, "lat": 9.9, "lon": 76.2, "speed": 1.2, "armed": true, "mode": "GUIDED",
			"depth": 12.0, "connected": true, "domain": domain, "twin": veh}
	if OS.has_environment("MCR_SHOT_FPV"):
		cam_f = 1.0; cam_target = 1.0
	for i in range(100):
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	img.save_png(OS.get_environment("MCR_SHOT"))
	get_tree().quit()

func _send(d: Dictionary):
	cmd.put_packet(JSON.stringify(d).to_utf8_buffer())

# ---------------- world ----------------
func _build_world():
	env = WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var ps := ProceduralSkyMaterial.new()
	ps.sky_top_color = Color(0.14, 0.34, 0.66)
	ps.sky_horizon_color = Color(0.62, 0.76, 0.86)
	ps.ground_horizon_color = Color(0.5, 0.6, 0.66)
	ps.sun_angle_max = 30.0
	sky.sky_material = ps
	e.sky = sky
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.glow_enabled = true
	e.glow_intensity = 0.5
	e.glow_bloom = 0.15
	e.ssr_enabled = true
	e.ssao_enabled = true
	e.fog_enabled = true
	e.fog_light_color = Color(0.66, 0.76, 0.83)
	e.fog_density = 0.0015
	env.environment = e
	add_child(env)

	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -40, 0)
	sun.light_energy = 1.3
	sun.shadow_enabled = true
	add_child(sun)

	# ocean: large subdivided plane with the Gerstner shader
	var ocean := MeshInstance3D.new()
	ocean.name = "OceanMesh"
	var pm := PlaneMesh.new()
	pm.size = Vector2(900, 900)
	pm.subdivide_width = 220
	pm.subdivide_depth = 220
	ocean.mesh = pm
	ocean_mat = ShaderMaterial.new()
	ocean_mat.shader = load("res://ocean.gdshader")
	ocean.material_override = ocean_mat
	add_child(ocean)

	seabed = _make_seabed()
	seabed.visible = false
	add_child(seabed)

	snow = _make_snow()
	snow.visible = false
	add_child(snow)

	# destination waypoint marker (a bright floating pylon)
	dest_marker = MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.4; cyl.bottom_radius = 0.4; cyl.height = 6.0
	dest_marker.mesh = cyl
	var mm := StandardMaterial3D.new()
	mm.albedo_color = Color(0.2, 1.0, 0.5)
	mm.emission_enabled = true; mm.emission = Color(0.2, 1.0, 0.5); mm.emission_energy_multiplier = 2.0
	dest_marker.material_override = mm
	dest_marker.visible = false
	add_child(dest_marker)

	cam = Camera3D.new()
	cam.fov = 64
	cam.far = 3000
	add_child(cam)

func _make_seabed() -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(900, 900)
	pm.subdivide_width = 80
	pm.subdivide_depth = 80
	mi.mesh = pm
	mi.position.y = -45
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.32, 0.29, 0.21)
	m.roughness = 0.95
	mi.material_override = m
	return mi

func _make_snow() -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = 400
	p.lifetime = 8.0
	p.visibility_aabb = AABB(Vector3(-40, -20, -40), Vector3(80, 40, 80))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(30, 15, 30)
	pm.gravity = Vector3(0, 0.15, 0)
	pm.initial_velocity_min = 0.05
	pm.initial_velocity_max = 0.2
	p.process_material = pm
	var sph := SphereMesh.new()
	sph.radius = 0.04
	sph.height = 0.08
	var sm := StandardMaterial3D.new()
	sm.albedo_color = Color(0.8, 0.86, 0.84, 0.6)
	sm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	sm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	sph.material = sm
	p.draw_pass_1 = sph
	return p

# ---------------- vehicle meshes ----------------
func _build_vehicle(kind: String):
	if vehicle:
		vehicle.queue_free()
	vehicle = Node3D.new()
	add_child(vehicle)
	vkind = kind
	match kind:
		"auv150": _make_auv(3.4, 0.42, true)
		"maya_auv": _make_auv(1.9, 0.19, false)
		"interceptor_usv": _make_interceptor()
		"survey_usv": _make_catamaran()
		_:
			if domain == "underwater": _make_auv(2.4, 0.3, false)
			else: _make_interceptor()

func _mat(c: Color, rough := 0.5, metal := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	m.metallic = metal
	return m

func _add(mesh: Mesh, mat: StandardMaterial3D, pos: Vector3, rot := Vector3.ZERO, scl := Vector3.ONE):
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.rotation_degrees = rot
	mi.scale = scl
	vehicle.add_child(mi)

func _emit_mat(c: Color, e: float, rough := 0.4) -> StandardMaterial3D:
	var m := _mat(c, rough, 0.0)
	m.emission_enabled = true
	m.emission = c
	m.emission_energy_multiplier = e
	return m

# surface of revolution about the Z (length) axis; profile = [Vector2(z, radius), ...]
func _revolved(profile: Array, radial := 26) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(profile.size() - 1):
		var zA: float = profile[i].x
		var rA: float = profile[i].y
		var zB: float = profile[i + 1].x
		var rB: float = profile[i + 1].y
		for j in range(radial):
			var a0 := TAU * float(j) / float(radial)
			var a1 := TAU * float(j + 1) / float(radial)
			var pA0 := Vector3(cos(a0) * rA, sin(a0) * rA, zA)
			var pA1 := Vector3(cos(a1) * rA, sin(a1) * rA, zA)
			var pB0 := Vector3(cos(a0) * rB, sin(a0) * rB, zB)
			var pB1 := Vector3(cos(a1) * rB, sin(a1) * rB, zB)
			st.add_vertex(pA0); st.add_vertex(pB0); st.add_vertex(pB1)
			st.add_vertex(pA0); st.add_vertex(pB1); st.add_vertex(pA1)
	st.generate_normals()
	return st.commit()

# loft a series of equal-size closed rings (Array of Array[Vector3])
func _lofted(sections: Array) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n: int = sections[0].size()
	for i in range(sections.size() - 1):
		var A: Array = sections[i]
		var B: Array = sections[i + 1]
		for j in range(n):
			var k := (j + 1) % n
			st.add_vertex(A[j]); st.add_vertex(B[j]); st.add_vertex(B[k])
			st.add_vertex(A[j]); st.add_vertex(B[k]); st.add_vertex(A[k])
	st.generate_normals()
	return st.commit()

# ---- AUV (torpedo): smooth ogive hull + X-fins + ducted prop; big => AUV-150 ----
func _make_auv(L: float, r: float, big: bool):
	var hz := L * 0.5
	var profile := [Vector2(-hz, 0.0), Vector2(-hz + r * 0.45, r * 0.6), Vector2(-hz + L * 0.22, r)]
	var nose0 := hz - L * 0.30
	profile.append(Vector2(nose0, r))
	var steps := 7
	for i in range(1, steps + 1):
		var t := float(i) / float(steps)
		profile.append(Vector2(lerp(nose0, hz, t), r * sqrt(max(0.0, 1.0 - t * t))))
	var hull_mat := _emit_mat(Color(0.96, 0.74, 0.11), 0.30, 0.45)   # high-vis survey yellow
	_add(_revolved(profile, 30), hull_mat, Vector3.ZERO)
	var dark := _mat(Color(0.12, 0.13, 0.15), 0.35, 0.2)
	# nose sonar cap
	_add(_revolved([Vector2(hz - r * 0.35, r * 0.78), Vector2(hz - r * 0.05, r * 0.5), Vector2(hz + 0.01, 0.0)], 24), dark, Vector3.ZERO)
	# dark instrument bands
	for zf in [-0.05, 0.12]:
		var band := CylinderMesh.new(); band.top_radius = r * 1.01; band.bottom_radius = r * 1.01; band.height = r * 0.18
		_add(band, dark, Vector3(0, 0, L * zf), Vector3(90, 0, 0))
	# X-tail fins
	var fin_mat := _mat(Color(0.2, 0.22, 0.26), 0.4, 0.1)
	for kk in range(4):
		var fin := BoxMesh.new(); fin.size = Vector3(0.03, r * 2.3, L * 0.13)
		_add(fin, fin_mat, Vector3(0, 0, -hz + L * 0.15), Vector3(0, 0, 45 + 90 * kk))
	# ducted aft propeller
	var duct := TorusMesh.new(); duct.inner_radius = r * 0.5; duct.outer_radius = r * 0.72
	_add(duct, _mat(Color(0.25, 0.26, 0.29), 0.5, 0.4), Vector3(0, 0, -hz + 0.02), Vector3(90, 0, 0))
	var hub := CylinderMesh.new(); hub.top_radius = r * 0.16; hub.bottom_radius = r * 0.16; hub.height = r * 0.5
	_add(hub, _mat(Color(0.3, 0.3, 0.33), 0.5, 0.5), Vector3(0, 0, -hz + 0.04), Vector3(90, 0, 0))
	for kk in range(4):
		var bl := BoxMesh.new(); bl.size = Vector3(r * 0.5, 0.02, r * 0.14)
		_add(bl, _mat(Color(0.33, 0.33, 0.36), 0.5, 0.4), Vector3(0, 0, -hz + 0.04), Vector3(0, 0, 45 + 90 * kk))
	if big:
		# AUV-150: lateral thruster pods + dorsal sensor mast/beacon
		for s in [-1.0, 1.0]:
			var pod := _revolved([Vector2(-0.3, 0.0), Vector2(-0.24, 0.08), Vector2(0.24, 0.08), Vector2(0.3, 0.0)], 16)
			_add(pod, dark, Vector3(s * (r + 0.15), -r * 0.2, -hz + L * 0.34), Vector3(0, 90, 0))
		var mast := BoxMesh.new(); mast.size = Vector3(0.05, r * 0.9, 0.1)
		_add(mast, fin_mat, Vector3(0, r + r * 0.4, hz - L * 0.4))
		var bcn := SphereMesh.new(); bcn.radius = 0.055; bcn.height = 0.11
		_add(bcn, _emit_mat(Color(1.0, 0.3, 0.22), 3.0), Vector3(0, r + r * 0.95, hz - L * 0.4))

# ---- interceptor USV: sleek naval monohull, lofted hull + console + mast ----
func _make_interceptor():
	var L := 7.5
	var hb := 0.95
	var outline := [
		Vector2(-1.00, 0.55), Vector2(-1.00, 0.08), Vector2(-0.9, -0.10),
		Vector2(-0.5, -0.30), Vector2(0.0, -0.36), Vector2(0.5, -0.30),
		Vector2(0.9, -0.10), Vector2(1.00, 0.08), Vector2(1.00, 0.55), Vector2(0.0, 0.55)
	]
	var stations := [
		[-L * 0.5, 0.82, 0.0], [-L * 0.25, 1.0, 0.03], [0.0, 1.0, 0.06],
		[L * 0.25, 0.8, 0.17], [L * 0.42, 0.45, 0.35], [L * 0.5, 0.06, 0.52]
	]
	var sections := []
	for stn in stations:
		var ring := []
		for p in outline:
			ring.append(Vector3(p.x * hb * stn[1], p.y + stn[2], stn[0]))
		sections.append(ring)
	_add(_lofted(sections), _mat(Color(0.32, 0.37, 0.43), 0.4), Vector3.ZERO)        # naval grey
	# transom plate (stern cap)
	var transom := BoxMesh.new(); transom.size = Vector3(hb * 1.64, 0.9, 0.05)
	_add(transom, _mat(Color(0.28, 0.32, 0.37), 0.4), Vector3(0, 0.1, -L * 0.5))
	# deck
	var deck := BoxMesh.new(); deck.size = Vector3(hb * 1.5, 0.06, L * 0.74)
	_add(deck, _mat(Color(0.74, 0.77, 0.80), 0.5), Vector3(0, 0.5, -L * 0.03))
	# waterline accent stripe
	var stripe := BoxMesh.new(); stripe.size = Vector3(hb * 2.04, 0.1, L * 0.92)
	_add(stripe, _mat(Color(0.74, 0.16, 0.16), 0.3), Vector3(0, 0.14, 0))
	# center console + raked windshield
	var cab := BoxMesh.new(); cab.size = Vector3(hb * 1.1, 0.6, L * 0.18)
	_add(cab, _mat(Color(0.26, 0.3, 0.36), 0.4), Vector3(0, 0.82, -L * 0.02))
	var ws := BoxMesh.new(); ws.size = Vector3(hb * 1.0, 0.34, 0.06)
	_add(ws, _mat(Color(0.3, 0.45, 0.6), 0.1, 0.1), Vector3(0, 1.02, L * 0.07), Vector3(-22, 0, 0))
	# radar mast + scanner
	var mast := BoxMesh.new(); mast.size = Vector3(0.08, 1.1, 0.08)
	_add(mast, _mat(Color(0.12, 0.13, 0.15), 0.4), Vector3(0, 1.5, -L * 0.08))
	var radar := BoxMesh.new(); radar.size = Vector3(0.75, 0.06, 0.16)
	_add(radar, _mat(Color(0.8, 0.82, 0.85), 0.5), Vector3(0, 2.05, -L * 0.08))

# ---- survey USV: twin-hull catamaran + survey gear + downward sonar pole ----
func _make_catamaran():
	var L := 4.4
	var sep := 1.05
	var r := 0.3
	var hull_mat := _emit_mat(Color(0.95, 0.66, 0.11), 0.12, 0.4)     # survey orange
	var dark := _mat(Color(0.12, 0.13, 0.15), 0.4)
	var hz := L * 0.5
	var prof := [Vector2(-hz, 0.0), Vector2(-hz + 0.3, r * 0.7), Vector2(-hz + L * 0.2, r), Vector2(hz - L * 0.32, r)]
	var n0 := hz - L * 0.32
	for i in range(1, 6):
		var t := float(i) / 5.0
		prof.append(Vector2(lerp(n0, hz, t), r * sqrt(max(0.0, 1.0 - t * t))))
	for s in [-1.0, 1.0]:
		_add(_revolved(prof, 22), hull_mat, Vector3(s * sep, -0.05, 0))
		var hub := CylinderMesh.new(); hub.top_radius = 0.06; hub.bottom_radius = 0.06; hub.height = 0.1
		_add(hub, _mat(Color(0.3, 0.3, 0.33), 0.5, 0.5), Vector3(s * sep, -0.05, -hz + 0.02), Vector3(90, 0, 0))
	# cross deck
	var deck := BoxMesh.new(); deck.size = Vector3(sep * 2 + r * 1.6, 0.12, L * 0.62)
	_add(deck, _mat(Color(0.2, 0.22, 0.26), 0.5), Vector3(0, r * 0.9, 0))
	# equipment box + antenna mast
	var eq := BoxMesh.new(); eq.size = Vector3(sep * 0.9, 0.5, L * 0.28)
	_add(eq, _mat(Color(0.8, 0.82, 0.85), 0.5), Vector3(0, r * 0.9 + 0.3, -L * 0.02))
	var mast := BoxMesh.new(); mast.size = Vector3(0.06, 0.8, 0.06)
	_add(mast, dark, Vector3(0, r * 0.9 + 0.9, -L * 0.08))
	# downward multibeam sonar pole between the hulls
	var pole := CylinderMesh.new(); pole.top_radius = 0.05; pole.bottom_radius = 0.05; pole.height = 0.7
	_add(pole, dark, Vector3(0, -r * 0.6, L * 0.05))
	var head := BoxMesh.new(); head.size = Vector3(0.18, 0.12, 0.25)
	_add(head, _mat(Color(0.15, 0.16, 0.18), 0.4, 0.2), Vector3(0, -r * 1.0, L * 0.05))

# ---------------- per-frame ----------------
func _process(delta):
	_poll_net()
	if ocean_mat:
		ocean_mat.set_shader_parameter("time", Time.get_ticks_msec() / 1000.0)
	_update_vehicle()
	_update_camera(delta)
	_update_hud()

func _poll_net():
	while net.get_available_packet_count() > 0:
		var pkt := net.get_packet()
		var d = JSON.parse_string(pkt.get_string_from_utf8())
		if d == null:
			continue
		tele = d
		connected = d.get("connected", false)
		booting = d.get("booting", false)
		if d.has("home"):
			home = Vector2(d["home"][0], d["home"][1])
		if d.has("domain") and d["domain"] != domain:
			domain = d["domain"]
		if d.has("twin") and d["twin"] != vkind:
			_build_vehicle(d["twin"])
			_apply_domain_visuals()
			# keep the attack menu in sync with the (possibly new) domain, so a
			# backend-driven twin switch matches what the menu-driven path does
			if not labels.is_empty() and labels.has("_atk_base_y"):
				_rebuild_attack_buttons(int(get_viewport().size.x - 300 + 16), labels["_atk_base_y"])
		if d.has("waves") and ocean_mat:
			ocean_mat.set_shader_parameter("hs", d["waves"].get("hs", 1.2))
			ocean_mat.set_shader_parameter("tp", d["waves"].get("tp", 7.0))
			ocean_mat.set_shader_parameter("dir_deg", d["waves"].get("bearing", 160.0))
		active_attack = d.get("active_attack", "")

func _apply_domain_visuals():
	var e := env.environment
	if domain == "underwater":
		e.background_mode = Environment.BG_COLOR
		e.background_color = Color(0.03, 0.13, 0.18)
		e.fog_density = 0.03
		e.fog_light_color = Color(0.05, 0.22, 0.30)
		seabed.visible = true
		snow.visible = true
		snow.emitting = true
	else:
		e.background_mode = Environment.BG_SKY
		e.fog_density = 0.0015
		e.fog_light_color = Color(0.66, 0.76, 0.83)
		seabed.visible = false
		snow.visible = false

var veh_pos := Vector3.ZERO    # smoothed world position of the vehicle

# Telemetry lat/lon (+depth) -> world metres. World: x=east, z=-north, y=-depth.
func _tele_world() -> Vector3:
	var lat: float = float(tele.get("lat")) if tele.get("lat") != null else home.x
	var lon: float = float(tele.get("lon")) if tele.get("lon") != null else home.y
	var north: float = (lat - home.x) * DEG_M
	var east: float = (lon - home.y) * DEG_M * cos(deg_to_rad(home.x))
	var y: float = (-float(tele.get("depth", 0.0))) if domain == "underwater" else 0.0
	return Vector3(east, y, -north)

func _update_vehicle():
	if not vehicle:
		return
	heading = float(tele.get("hdg", 0.0))
	vehicle.rotation_degrees = Vector3(0, -heading, 0)
	# move the vehicle to its telemetry position (smoothed so UDP jitter is calm)
	var target := _tele_world()
	veh_pos = veh_pos.lerp(target, 0.15) if connected else target
	vehicle.position = veh_pos
	# keep the ocean/seabed/particles centred on the vehicle so it never sails
	# off the finite meshes (waves are world-space in the shader, so this reads
	# as the vehicle moving through the water, not the water following it).
	var c := Vector3(veh_pos.x, 0, veh_pos.z)
	_recenter_world(c)
	if dest_marker:
		dest_marker.visible = dest_world != null
		if dest_world != null:
			dest_marker.position = Vector3(dest_world.x, 0.5, dest_world.z)

func _recenter_world(c: Vector3):
	for n in [seabed, snow]:
		if n:
			n.position.x = c.x
			n.position.z = c.z
	# ocean mesh is large; recentre it too so its edges never show
	var ocean := get_node_or_null("OceanMesh")
	if ocean:
		ocean.position.x = c.x
		ocean.position.z = c.z

func _update_camera(delta):
	var hd := deg_to_rad(heading)
	var fwd := Vector3(sin(hd), 0, -cos(hd))
	var eye_fpv: Vector3
	var ctr_fpv: Vector3
	var eye_3rd: Vector3
	var ctr_3rd: Vector3
	if domain == "underwater":
		eye_fpv = -fwd * 6.5 + Vector3(0, 2.2, 0); ctr_fpv = fwd * 9 + Vector3(0, -1.5, 0)
		eye_3rd = -fwd * 11 + Vector3(0, 5.5, 0); ctr_3rd = fwd * 2 + Vector3(0, -2.5, 0)
	else:
		eye_fpv = -fwd * 8 + Vector3(0, 3.0, 0); ctr_fpv = fwd * 14
		eye_3rd = -fwd * 26 + Vector3(0, 17, 0); ctr_3rd = fwd * 6 + Vector3(0, -1, 0)
	# ease cam_f toward target
	if cam_f < cam_target:
		cam_f = min(cam_target, cam_f + delta / 1.6)
	elif cam_f > cam_target:
		cam_f = max(cam_target, cam_f - delta / 1.0)
	# camera offsets are relative to the vehicle, so the camera follows it
	var eye = veh_pos + eye_3rd.lerp(eye_fpv, cam_f)
	var ctr = veh_pos + ctr_3rd.lerp(ctr_fpv, cam_f)
	cam.position = eye
	cam.look_at(ctr, Vector3.UP)
	cam.fov = 64 - 6 * cam_f

# ---------------- HUD ----------------
func _lbl(parent: Node, txt: String, pos: Vector2, size := 14, col := Color(0.82, 0.86, 0.9)) -> Label:
	var l := Label.new()
	l.text = txt
	l.position = pos
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE   # labels never swallow clicks
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	parent.add_child(l)
	return l

func _btn(parent: Node, txt: String, pos: Vector2, sz: Vector2, cb: Callable) -> Button:
	var b := Button.new()
	b.text = txt
	b.position = pos
	b.size = sz
	b.pressed.connect(cb)
	parent.add_child(b)
	return b

func _build_hud():
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	hud = Control.new()
	hud.set_anchors_preset(Control.PRESET_FULL_RECT)
	# CRITICAL: a full-rect Control defaults to MOUSE_FILTER_STOP and would
	# swallow every click across the whole screen -- blocking the 3D destination
	# raycast (_unhandled_input) and the menu. IGNORE lets clicks through; the
	# Button children keep their own STOP filter so they still work.
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(hud)
	var panel := Panel.new()
	panel.position = Vector2(get_viewport().size.x - 300, 0)
	panel.size = Vector2(300, get_viewport().size.y)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(panel)
	var px := panel.position.x + 16
	labels["title"] = _lbl(hud, "MARITIME CYBER RANGE", Vector2(18, 12), 16, Color(0.8, 0.9, 1.0))
	labels["status"] = _lbl(hud, "IDLE", Vector2(get_viewport().size.x - 110, 14), 13, Color(0.9, 0.8, 0.5))
	var y := 20
	for k in ["LAT", "LON", "HDG", "SOG", "DEPTH", "MODE", "ARMED", "DEST"]:
		_lbl(hud, k, Vector2(px, y), 11, Color(0.55, 0.62, 0.70))
		labels[k] = _lbl(hud, "--", Vector2(px + 72, y), 13)
		y += 22
	y += 10
	_btn(hud, "ARM", Vector2(px, y), Vector2(84, 30), func(): _send({"cmd": "arm"}))
	_btn(hud, "DISARM", Vector2(px + 92, y), Vector2(84, 30), func(): _send({"cmd": "disarm"}))
	_btn(hud, "SWITCH", Vector2(px + 184, y), Vector2(84, 30), func(): menu.visible = true)
	y += 38
	_btn(hud, "SET DESTINATION", Vector2(px, y), Vector2(268, 30), func(): setting_dest = not setting_dest)
	y += 42
	labels["atk_y"] = _lbl(hud, "ATTACKS", Vector2(px, y), 11, Color(0.55, 0.62, 0.70))
	y += 20
	labels["_atk_base"] = Label.new(); labels["_atk_base_y"] = y   # store base for attack buttons rebuilt per domain
	_rebuild_attack_buttons(px, y)
	# event/status line
	labels["evt"] = _lbl(hud, "", Vector2(px, get_viewport().size.y - 60), 12, Color(0.7, 0.8, 0.85))
	_btn(hud, "STOP & QUIT", Vector2(px, get_viewport().size.y - 36), Vector2(268, 28), func(): _quit())

var atk_buttons := []
func _rebuild_attack_buttons(px: int, y0: int):
	for b in atk_buttons:
		b.queue_free()
	atk_buttons.clear()
	var atks := (["Acoustic spoof", "C2 mode", "C2 override"] if domain == "underwater"
		else ["GPS spoof", "C2 mode", "C2 override", "AIS ghost"])
	var y := y0
	for a in atks:
		var b := _btn(hud, a, Vector2(px, y), Vector2(268, 30), _attack_cb(a))
		atk_buttons.append(b)
		y += 34
	var sb := _btn(hud, "STOP ATTACK", Vector2(px, y), Vector2(268, 28), func(): _send({"cmd": "stop"}))
	atk_buttons.append(sb)

func _attack_cb(name: String) -> Callable:
	return func(): _send({"cmd": "attack", "name": name})

func _update_hud():
	if labels.is_empty():
		return
	labels["status"].text = ("LIVE" if connected else ("BOOTING" if booting else "IDLE"))
	labels["status"].add_theme_color_override("font_color",
		Color(0.4, 0.8, 0.55) if connected else Color(0.9, 0.7, 0.4))
	labels["LAT"].text = "%.5f" % float(tele.get("lat", 0)) if tele.get("lat") else "--"
	labels["LON"].text = "%.5f" % float(tele.get("lon", 0)) if tele.get("lon") else "--"
	labels["HDG"].text = "%05.1f" % float(tele.get("hdg", 0))
	labels["SOG"].text = "%.2f m/s" % float(tele.get("speed", 0))
	labels["DEPTH"].text = ("%.1f m" % float(tele.get("depth", 0))) if domain == "underwater" else "surface"
	labels["MODE"].text = str(tele.get("mode", "--"))
	labels["ARMED"].text = "ARMED" if tele.get("armed", false) else "SAFE"
	labels["ARMED"].add_theme_color_override("font_color",
		Color(0.85, 0.4, 0.4) if tele.get("armed", false) else Color(0.4, 0.8, 0.55))
	if setting_dest:
		labels["DEST"].text = "click the water…"
		labels["DEST"].add_theme_color_override("font_color", Color(0.5, 0.9, 0.6))
	elif dest_rel:
		labels["DEST"].text = "%.0f m" % dest_rel.length()
		labels["DEST"].add_theme_color_override("font_color", Color(0.82, 0.86, 0.9))
	labels["evt"].text = str(tele.get("event", ""))

# ---------------- menu ----------------
var site_btns := []
var twin_btns := []

func _pick_site(idx: int):
	sel_site = idx
	_refresh_menu_sel()

func _pick_twin(idx: int):
	sel_twin = idx
	_refresh_menu_sel()

func _refresh_menu_sel():
	for i in site_btns.size():
		site_btns[i].modulate = Color(0.5, 1.0, 0.6) if i == sel_site else Color(1, 1, 1)
	for i in twin_btns.size():
		twin_btns[i].modulate = Color(0.5, 1.0, 0.6) if i == sel_twin else Color(1, 1, 1)

func _build_menu():
	var layer := CanvasLayer.new()
	layer.layer = 10          # above the HUD (layer 5) so it is unambiguously on top
	add_child(layer)
	menu = Control.new()
	menu.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(menu)
	var bg := ColorRect.new(); bg.color = Color(0.05, 0.07, 0.09, 0.96)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	menu.add_child(bg)
	_lbl(menu, "MARITIME CYBER RANGE", Vector2(80, 70), 24, Color(0.5, 0.9, 0.6))
	_lbl(menu, "Select a test site and a vehicle, then START RUN.", Vector2(80, 110), 14, Color(0.6, 0.7, 0.75))
	_lbl(menu, "SITE", Vector2(80, 160), 12, Color(0.55, 0.62, 0.70))
	for i in SITES.size():
		var b := _btn(menu, SITES[i].capitalize(), Vector2(80 + i * 200, 185), Vector2(180, 40),
			_pick_site.bind(i))
		site_btns.append(b)
	_lbl(menu, "VEHICLE", Vector2(80, 245), 12, Color(0.55, 0.62, 0.70))
	for i in TWINS.size():
		var b := _btn(menu, TWINS[i]["name"], Vector2(80 + (i % 2) * 360, 270 + (i / 2) * 54), Vector2(340, 44),
			_pick_twin.bind(i))
		twin_btns.append(b)
	_btn(menu, "START RUN", Vector2(80, 420), Vector2(240, 48), func(): _start())
	_refresh_menu_sel()

func _start():
	var tw = TWINS[sel_twin]
	domain = tw["dom"]
	_build_vehicle(tw["id"])
	_apply_domain_visuals()
	_rebuild_attack_buttons(int(get_viewport().size.x - 300 + 16), labels["_atk_base_y"])
	_send({"cmd": "boot", "site": SITES[sel_site], "twin": tw["id"], "domain": tw["dom"]})
	menu.visible = false
	cam_f = 0.0; cam_target = 0.0; dest_rel = null; setting_dest = false

# ---------------- input (destination picking) ----------------
func _unhandled_input(ev):
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		if setting_dest and connected:
			_pick_destination(ev.position)

func _pick_destination(mp: Vector2):
	var from = cam.project_ray_origin(mp)
	var dir = cam.project_ray_normal(mp)
	if abs(dir.y) < 1e-4:
		return
	var t = -from.y / dir.y
	if t < 0:
		return
	var hit = from + dir * t          # world (x=east, z=-north)
	# offset of the click from the VEHICLE's current world position
	var d := Vector2(hit.x - veh_pos.x, (-hit.z) - (-veh_pos.z))
	if d.length() > 300:
		d = d.normalized() * 300
	dest_rel = d
	dest_world = Vector3(veh_pos.x + d.x, 0, veh_pos.z - d.y)
	if dest_marker:
		dest_marker.visible = true
		dest_marker.position = Vector3(dest_world.x, 0.5, dest_world.z)
	# convert the offset to an absolute lat/lon from the vehicle's fix
	var vlat = float(tele.get("lat")) if tele.get("lat") != null else home.x
	var vlon = float(tele.get("lon")) if tele.get("lon") != null else home.y
	var lat = vlat + d.y / DEG_M
	var lon = vlon + d.x / (DEG_M * cos(deg_to_rad(vlat)))
	_send({"cmd": "goto", "lat": lat, "lon": lon})
	setting_dest = false
	cam_target = 1.0                   # smooth transition to first-person

func _quit():
	_send({"cmd": "quit"})
	await get_tree().create_timer(0.2).timeout
	get_tree().quit()
