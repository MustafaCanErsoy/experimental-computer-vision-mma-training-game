extends Node3D
## Camera-free dark-fantasy encounter preview. All scene geometry is procedural.

const Encounter = preload("res://encounter.gd")
const ProgressStore = preload("res://progress_store.gd")
const NAMES = {"left_punch": "SOL YUMRUK", "right_punch": "SAĞ YUMRUK", "uppercut": "AŞAĞIDAN VUR"}
var encounter = Encounter.new()
var camera: Camera3D
var guardian: Node3D
var seal: MeshInstance3D
var gate: Node3D
var title: Label
var prompt: Label
var help: Label
var feedback: Label
var counters: Label
var health_bar: ProgressBar
var timer_bar: ProgressBar
var fists: Array[Node3D] = []
var shards: Array[Dictionary] = []
var clock: float = 0.0
var event_id: int = 0
var recoil: float = 0.0
var feedback_time: float = 0.0
var warm_material: StandardMaterial3D
var stone: Array[StandardMaterial3D] = []
var iron: StandardMaterial3D
var ash: StandardMaterial3D
var ember: StandardMaterial3D
var sky_light: DirectionalLight3D
var smoke_test: bool = false
var gate_tween: Tween
var fist_tweens: Dictionary = {}
var bridge = null
var badge: Label
var input_kind: String = "keyboard"
var progress_store
var result_panel: ColorRect
var result_title: Label
var result_stats: Label
var result_record: Label
var result_status: Label
var result_saved: bool = false
var save_enabled: bool = true
var diagnostic_label: Label
var report_file: String = ""

func material(color: Color, metal: float = 0.0, glow: float = 0.0) -> StandardMaterial3D:
	var m = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.83
	m.metallic = metal
	if glow > 0:
		m.emission_enabled = true
		m.emission = color
		m.emission_energy_multiplier = glow
	return m

func box(parent: Node3D, pos: Vector3, size: Vector3, mat: Material) -> MeshInstance3D:
	var mesh = BoxMesh.new()
	mesh.size = size
	return shape(parent, pos, mesh, mat)

func shape(parent: Node3D, pos: Vector3, mesh: Mesh, mat: Material) -> MeshInstance3D:
	var node = MeshInstance3D.new()
	node.mesh = mesh
	node.material_override = mat
	parent.add_child(node)
	node.position = pos
	return node

func cylinder(parent: Node3D, pos: Vector3, bottom: float, top: float, height: float, mat: Material) -> MeshInstance3D:
	var mesh = CylinderMesh.new()
	mesh.bottom_radius = bottom
	mesh.top_radius = top
	mesh.height = height
	mesh.radial_segments = 8
	return shape(parent, pos, mesh, mat)

func _ready() -> void:
	seed(7341)
	smoke_test = "--smoke" in OS.get_cmdline_user_args()
	save_enabled = not smoke_test and "--no-save" not in OS.get_cmdline_user_args()
	progress_store = ProgressStore.new()
	var input_source = ""
	var input_port = 28741
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report-file="):
			report_file = arg.trim_prefix("--report-file=")
		if arg.begins_with("--source="):
			input_source = arg.trim_prefix("--source=")
		if arg.begins_with("--port="):
			input_port = int(arg.trim_prefix("--port="))
	if input_source != "":
		if input_source not in ["synthetic", "camera"] or input_port < 1 or input_port > 65535:
			push_error("Invalid local input source or port")
			get_tree().quit(2)
			return
		bridge = preload("res://event_bridge.gd").new()
		input_kind = input_source
		encounter.timed = input_kind != "camera"
		bridge.start(input_source, input_port)
		bridge.strike_received.connect(show_strike)
		bridge.prompt_expired.connect(missed_prompt)
		clock = Time.get_ticks_usec() / 1000000.0
		encounter.set_paused(true, clock)
	for i in range(5):
		stone.append(material(Color(0.20 + i * 0.016, 0.205 + i * 0.014, 0.21 + i * 0.012)))
	iron = material(Color("383b3c"), 0.65)
	ash = material(Color("15161b"))
	ember = material(Color("c47832"), 0.1, 1.7)
	warm_material = material(Color("be9b5d"), 0.35, 0.4)
	build_room()
	build_guardian()
	build_ui()
	refresh_ui()
	if smoke_test:
		if "--results" in OS.get_cmdline_user_args():
			# Exercise the real completion path for a camera-free rendered preview.
			for floor_index in range(Encounter.SESSION_FLOORS):
				encounter.begin(clock)
				while encounter.phase == "fight":
					event_id += 1
					show_strike(encounter.requested(), encounter.strike(encounter.requested(), event_id, clock))
				if encounter.phase == "cleared":
					encounter.climb(clock)
					reset_floor()
			refresh_ui()
		if "--fight" in OS.get_cmdline_user_args():
			camera.position.z = 2.6
			encounter.begin(clock)
			refresh_ui()
		await get_tree().process_frame
		await get_tree().process_frame
		print("Tower scene built: ", get_child_count(), " root nodes; input source: ", input_kind)
		if "--capture" in OS.get_cmdline_user_args():
			await RenderingServer.frame_post_draw
			var image = get_viewport().get_texture().get_image()
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://../reports"))
			var result = image.save_png(ProjectSettings.globalize_path("res://../reports/tower-preview.png"))
			print("Rendered game-only screenshot: ", result)
		get_tree().quit()

func build_room() -> void:
	var environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("101319")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("9199a8")
	environment.ambient_light_energy = 0.5
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.fog_enabled = true
	environment.fog_light_color = Color("1c2029")
	environment.fog_density = 0.025
	var world = WorldEnvironment.new()
	world.environment = environment
	add_child(world)
	sky_light = DirectionalLight3D.new()
	sky_light.rotation_degrees = Vector3(-50, -28, 0)
	sky_light.light_color = Color("b4bfd1")
	sky_light.light_energy = 1.1
	sky_light.shadow_enabled = true
	add_child(sky_light)
	for x in range(-4, 4):
		for z in range(-6, 5):
			box(self, Vector3(x * 1.7 + 0.85, -0.18, z * 1.7), Vector3(1.66, 0.35, 1.66), stone[randi() % 5])
	for side in [-1, 1]:
		for z in range(-9, 9, 2):
			for y in range(4):
				box(self, Vector3(side * 7, y * 1.5 + 0.6, z), Vector3(0.65, 1.46, 1.94), stone[randi() % 5])
		for z in [-7, -2, 3, 7]:
			cylinder(self, Vector3(side * 5.6, 2.25, z), 0.42, 0.32, 4.5, stone[2])
			box(self, Vector3(side * 5.6, 0.22, z), Vector3(1.05, 0.45, 1.05), stone[3])
			box(self, Vector3(side * 5.6, 4.4, z), Vector3(1.1, 0.45, 1.1), stone[1])
		for z in [-5, 3]:
			cylinder(self, Vector3(side * 4.4, 0.7, z), 0.15, 0.1, 1.4, iron)
			cylinder(self, Vector3(side * 4.4, 1.48, z), 0.16, 0.35, 0.18, iron)
			cylinder(self, Vector3(side * 4.4, 1.74, z), 0.22, 0.03, 0.42, ember)
			var flame = OmniLight3D.new()
			flame.position = Vector3(side * 4.4, 2.0, z)
			flame.light_color = Color("edab62")
			flame.light_energy = 3.5
			flame.omni_range = 5.5
			add_child(flame)
		box(self, Vector3(side * 4.65, 3.0, -10), Vector3(5.0, 6.0, 0.65), stone[0])
		box(self, Vector3(side * 2.0, 2.0, -9.7), Vector3(0.7, 4.0, 0.9), stone[3])
	for i in range(11):
		var angle = float(i) / 10.0 * PI
		var block = box(self, Vector3(cos(angle) * 2, 4 + sin(angle) * 2, -9.7), Vector3(0.65, 0.68, 0.9), stone[2])
		block.rotation.z = angle - PI * 0.5
	for i in range(7):
		box(self, Vector3(0, 0.13 + i * 0.16, -6.3 - i * 0.48), Vector3(3.2, 0.26 + i * 0.32, 0.5), stone[i % 5])
	gate = Node3D.new()
	add_child(gate)
	gate.position = Vector3(0, 1.1, -9.4)
	for i in range(-3, 4):
		box(gate, Vector3(i * 0.48, 1.8, 0), Vector3(0.10, 3.6, 0.16), iron)
	box(gate, Vector3(0, 2.7, 0), Vector3(3.2, 0.16, 0.2), iron)
	for i in range(30):
		var side = -1 if i % 2 == 0 else 1
		var rubble = box(self, Vector3(side * randf_range(5.8, 6.7), 0.18, randf_range(-8, 7)), Vector3(randf_range(0.2, 0.6), 0.4, randf_range(0.3, 0.7)), stone[i % 5])
		rubble.rotation = Vector3(randf(), randf() * 3, randf())
	camera = Camera3D.new()
	add_child(camera)
	camera.position = Vector3(0, 1.85, 7.2)
	camera.fov = 67
	camera.current = true
	for side in [-1, 1]:
		var fist = Node3D.new()
		camera.add_child(fist)
		fist.position = Vector3(side * 0.38, -0.25, -0.67)
		box(fist, Vector3.ZERO, Vector3(0.19, 0.19, 0.23), iron)
		box(fist, Vector3(0, -0.05, 0.20), Vector3(0.15, 0.16, 0.32), ash)
		box(fist, Vector3(0, 0.04, -0.12), Vector3(0.21, 0.08, 0.06), warm_material)
		fists.append(fist)

func build_guardian() -> void:
	guardian = Node3D.new()
	add_child(guardian)
	guardian.position = Vector3(0, 0, -2.5)
	cylinder(guardian, Vector3(0, 1.0, -0.12), 0.68, 0.44, 1.8, ash)
	for side in [-1, 1]:
		box(guardian, Vector3(side * 0.23, 0.42, 0.16), Vector3(0.29, 0.8, 0.3), iron)
		box(guardian, Vector3(side * 0.23, 0.1, 0.27), Vector3(0.33, 0.2, 0.52), iron)
		var shoulder = box(guardian, Vector3(side * 0.59, 1.79, 0), Vector3(0.46, 0.30, 0.55), iron)
		shoulder.rotation.z = side * -0.22
		var arm = box(guardian, Vector3(side * 0.61, 1.37, 0.15), Vector3(0.28, 0.64, 0.3), iron)
		arm.rotation.x = -0.28
		box(guardian, Vector3(side * 0.61, 1.11, 0.28), Vector3(0.30, 0.29, 0.34), iron)
		var horn = cylinder(guardian, Vector3(side * 0.29, 2.46, -0.02), 0.12, 0.01, 0.65, iron)
		horn.rotation.z = side * -0.38
	box(guardian, Vector3(0, 1.53, 0.04), Vector3(0.87, 0.89, 0.48), iron)
	box(guardian, Vector3(0, 1.57, 0.3), Vector3(0.08, 0.8, 0.08), warm_material)
	box(guardian, Vector3(0, 1.16, 0.05), Vector3(0.93, 0.12, 0.54), warm_material)
	box(guardian, Vector3(0, 2.14, 0.03), Vector3(0.49, 0.54, 0.45), iron)
	box(guardian, Vector3(0, 2.14, 0.265), Vector3(0.41, 0.055, 0.02), ember)
	box(guardian, Vector3(0, 2.04, 0.29), Vector3(0.07, 0.24, 0.07), iron)
	var ring = TorusMesh.new()
	ring.inner_radius = 0.35
	ring.outer_radius = 0.38
	seal = shape(guardian, Vector3(0, 1.5, 0.5), ring, warm_material)
	seal.rotation.x = PI * 0.5
	seal.visible = false

func label(parent: Control, pos: Vector2, size: Vector2, text_size: int, color: Color, centered: bool = false) -> Label:
	var node = Label.new()
	parent.add_child(node)
	node.position = pos
	node.size = size
	node.add_theme_font_size_override("font_size", text_size)
	node.add_theme_color_override("font_color", color)
	if centered:
		node.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	return node

func build_ui() -> void:
	var canvas = CanvasLayer.new()
	add_child(canvas)
	var ui = Control.new()
	canvas.add_child(ui)
	ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var top = ColorRect.new()
	ui.add_child(top)
	top.size = Vector2(1280, 133)
	top.color = Color(0.025, 0.027, 0.032, 0.90)
	var brand = label(ui, Vector2(40, 18), Vector2(850, 24), 14, Color("b59a6d"))
	brand.text = "S H A D O W M M A    /    K A R A N L I K   K U L E"
	title = label(ui, Vector2(40, 48), Vector2(830, 48), 30, Color("e2d9c7"))
	badge = label(ui, Vector2(860, 25), Vector2(380, 74), 14, Color("c9ad7a"))
	badge.text = "GELİŞTİRME DEMOSU\nKamera kapalı · Vuruşlar klavyeden"
	if bridge:
		badge.text = "SENTETİK BAĞLANTI DEMOSU\nKamera kapalı · Python olayları" if bridge.source == "synthetic" else "DENEYSEL KAMERA BAĞLANTISI\nİnsanla doğrulanmadı"
	counters = label(ui, Vector2(40, 98), Vector2(900, 25), 15, Color("aaa99f"))
	var bottom = ColorRect.new()
	ui.add_child(bottom)
	bottom.position = Vector2(0, 622)
	bottom.size = Vector2(1280, 178)
	bottom.color = Color(0.025, 0.027, 0.032, 0.93)
	prompt = label(ui, Vector2(180, 633), Vector2(920, 46), 29, Color("edddbb"), true)
	feedback = label(ui, Vector2(140, 688), Vector2(1000, 26), 17, Color("bca789"), true)
	help = label(ui, Vector2(110, 730), Vector2(1060, 55), 16, Color("aaa99f"), true)
	health_bar = ProgressBar.new()
	ui.add_child(health_bar)
	health_bar.position = Vector2(410, 157)
	health_bar.size = Vector2(460, 9)
	health_bar.show_percentage = false
	style_bar(health_bar, Color("87463a"))
	health_bar.set_deferred("size", Vector2(460, 9))
	timer_bar = ProgressBar.new()
	ui.add_child(timer_bar)
	timer_bar.position = Vector2(490, 681)
	timer_bar.size = Vector2(300, 4)
	timer_bar.show_percentage = false
	style_bar(timer_bar, Color("b59a6d"))
	timer_bar.set_deferred("size", Vector2(300, 4))
	feedback.text = "Kül Muhafızı, üst kata çıkan yolu mühürledi."
	feedback_time = 6.0
	diagnostic_label = label(ui, Vector2(30, 474), Vector2(1220, 136), 17, Color("edddbb"))
	diagnostic_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	diagnostic_label.visible = input_kind == "camera"
	var diagnostic_background = StyleBoxFlat.new()
	diagnostic_background.bg_color = Color(0.025, 0.027, 0.032, 0.92)
	diagnostic_background.content_margin_left = 16
	diagnostic_background.content_margin_top = 10
	diagnostic_background.content_margin_right = 16
	diagnostic_background.content_margin_bottom = 10
	diagnostic_label.add_theme_stylebox_override("normal", diagnostic_background)
	result_panel = ColorRect.new()
	ui.add_child(result_panel)
	result_panel.position = Vector2(240, 164)
	result_panel.size = Vector2(800, 424)
	result_panel.color = Color(0.035, 0.037, 0.043, 0.97)
	result_panel.visible = false
	result_title = label(result_panel, Vector2(24, 25), Vector2(752, 44), 30, Color("e2d9c7"), true)
	var source_label = label(result_panel, Vector2(24, 78), Vector2(752, 40), 16, Color("c9ad7a"), true)
	source_label.text = {"keyboard": "KLAVYE DEMOSU · Kamera kapalı", "synthetic": "SENTETİK PYTHON DEMOSU · Kamera kapalı", "camera": "DENEYSEL KAMERA · İnsanla doğrulanmadı"}[input_kind]
	result_stats = label(result_panel, Vector2(40, 139), Vector2(720, 60), 23, Color("e2d9c7"), true)
	result_record = label(result_panel, Vector2(24, 224), Vector2(752, 72), 17, Color("b7b2a7"), true)
	result_status = label(result_panel, Vector2(24, 326), Vector2(752, 74), 15, Color("c9ad7a"), true)
	result_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func style_bar(bar: ProgressBar, color: Color) -> void:
	var background = StyleBoxFlat.new()
	background.bg_color = Color("27282a")
	var fill = StyleBoxFlat.new()
	fill.bg_color = color
	bar.add_theme_stylebox_override("background", background)
	bar.add_theme_stylebox_override("fill", fill)

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode == KEY_ESCAPE:
		get_tree().quit()
	elif event.keycode == KEY_F8 and input_kind == "camera":
		if not report_file.is_empty() and FileAccess.file_exists(report_file):
			OS.shell_open(report_file)
		else:
			feedback.text = "Rapor henüz hazır değil; kamera üreticisi bekleniyor."
	elif event.keycode == KEY_F9 and input_kind == "camera":
		bridge.control("frames_off" if bridge.recording else "frames_on")
	elif event.keycode == KEY_F10 and input_kind == "camera":
		bridge.control("calibrate")
	elif event.keycode == KEY_P:
		if bridge != null and input_kind == "camera":
			bridge.toggle_camera_pause(encounter, clock)
		elif not encounter.paused or bridge == null or (bridge.connected and bridge.source_ready):
			encounter.set_paused(not encounter.paused, clock)
	elif event.keycode == KEY_R:
		restart_session()
	elif event.keycode == KEY_F:
		encounter.finish(clock)
	elif event.keycode == KEY_K and encounter.phase == "results":
		save_result()
	elif not encounter.paused:
		if event.keycode == KEY_E and encounter.phase == "cleared" and camera.position.z < -5.4:
			if encounter.climb(clock):
				reset_floor()
		elif encounter.phase == "fight" and bridge == null:
			var moves = {KEY_1: "left_punch", KEY_2: "right_punch", KEY_3: "uppercut"}
			if moves.has(event.keycode):
				event_id += 1
				var outcome: String = encounter.strike(moves[event.keycode], event_id, clock)
				show_strike(moves[event.keycode], outcome)
	if bridge:
		bridge.sync(encounter)
	refresh_ui()

func restart_session() -> void:
	encounter = Encounter.new()
	encounter.timed = input_kind != "camera"
	result_saved = false
	event_id = 0
	if bridge:
		bridge.restart(encounter, clock)
	reset_floor()
	for index in fist_tweens:
		fist_tweens[index].kill()
	fist_tweens.clear()
	for index in range(fists.size()):
		fists[index].position = Vector3((-1 if index == 0 else 1) * 0.38, -0.25, -0.67)
	recoil = 0.0
	feedback.text = "Üç katlık yeni tırmanış · Muhafıza yaklaş."

func save_result() -> void:
	if not result_saved and save_enabled:
		result_saved = progress_store.record(input_kind, encounter.summary())

func show_strike(move: String, outcome: String) -> void:
	animate_punch(move)
	if outcome == "hit" or outcome == "defeated":
		recoil = 0.3
		feedback.text = "Mühür kırıldı · + puan"
		if outcome == "defeated":
			defeat_guardian()
	else:
		feedback.text = "İstenen hareketi bekle; seri sıfırlandı."
	feedback_time = 2.0

func missed_prompt() -> void:
	feedback.text = "Fırsat geçti · seri sıfırlandı"
	feedback_time = 1.5

func _exit_tree() -> void:
	if bridge:
		bridge.close()

func animate_punch(move: String) -> void:
	var index = 0 if move == "left_punch" or move == "uppercut" else 1
	var fist = fists[index]
	var home = Vector3((-1 if index == 0 else 1) * 0.38, -0.25, -0.67)
	if fist_tweens.has(index):
		fist_tweens[index].kill()
	if move == "uppercut":
		fist.position = home + Vector3(0, -0.25, 0)
	var tween = create_tween()
	fist_tweens[index] = tween
	tween.tween_property(fist, "position", home + (Vector3(0.12, 0.55, -0.35) if move == "uppercut" else Vector3(0, 0.16, -0.55)), 0.07)
	tween.tween_property(fist, "position", home, 0.15)

func _process(delta: float) -> void:
	clock += delta
	if bridge:
		# Wall monotonic time also expires leases across rendering stalls.
		clock = Time.get_ticks_usec() / 1000000.0
		bridge.poll(encounter, clock)
	if encounter.phase == "results":
		refresh_ui()
		return
	if encounter.paused:
		refresh_ui()
		return
	feedback_time -= delta
	if feedback_time < 0:
		feedback.text = ""
	var movement = Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP):
		movement.z -= 1
	if Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN):
		movement.z += 1
	if Input.is_physical_key_pressed(KEY_A):
		movement.x -= 1
	if Input.is_physical_key_pressed(KEY_D):
		movement.x += 1
	if input_kind == "camera":
		movement = Vector3.ZERO
		if bridge.has_guard(clock) and encounter.phase in ["approach", "cleared"]:
			movement.z = -1
	if encounter.phase != "fight":
		camera.position += movement.normalized() * delta * 3.3
		camera.position.x = clampf(camera.position.x, -3.1, 3.1)
		camera.position.z = clampf(camera.position.z, -7.1, 7.8)
		camera.position.y = 1.85 + maxf(0, -camera.position.z - 6.0) * 0.32
	if input_kind == "camera" and encounter.phase == "cleared" and camera.position.z < -5.4 and bridge.has_guard(clock):
		if encounter.climb(clock):
			reset_floor()
	if encounter.phase == "approach" and camera.position.z < 2.7:
		encounter.begin(clock)
		camera.position.x = 0
		camera.position.z = 2.6
		feedback.text = "Kül Muhafızı uyandı. Göğsündeki mührü parçala."
		feedback_time = 3.0
	if encounter.advance(clock):
		missed_prompt()
	if encounter.phase != "cleared":
		guardian.position.y = sin(clock * 1.6) * 0.035
		recoil = maxf(0, recoil - delta)
		guardian.rotation.x = -recoil * 0.6
		seal.rotation.z += delta * 0.35
	for item in shards:
		item.node.position += item.velocity * delta
		item.velocity.y -= 4.0 * delta
		item.node.rotation += Vector3(1, 2, 0.7) * delta
		if item.node.position.y < 0:
			item.node.position.y = 0
			item.velocity = Vector3.ZERO
	refresh_ui()
	if bridge:
		bridge.sync(encounter)

func defeat_guardian() -> void:
	guardian.visible = false
	seal.visible = false
	for i in range(24):
		var shard = box(self, guardian.position + Vector3(randf_range(-0.5, 0.5), randf_range(0.3, 2.5), 0.2), Vector3(0.16, 0.25, 0.15), iron if i % 3 else warm_material)
		shards.append({"node": shard, "velocity": Vector3(randf_range(-2, 2), randf_range(1, 4), randf_range(-1, 2))})
	gate_tween = create_tween()
	gate_tween.tween_property(gate, "position:y", 5.0, 1.4)
	feedback.text = "MUHAFIZ YENİLDİ · Yol açıldı"
	feedback_time = 5.0

func reset_floor() -> void:
	if gate_tween:
		gate_tween.kill()
	for item in shards:
		item.node.queue_free()
	shards.clear()
	guardian.visible = true
	guardian.rotation = Vector3.ZERO
	gate.position.y = 1.1
	camera.position = Vector3(0, 1.85, 7.2)
	feedback.text = "Daha yukarıda aynı karanlık bekliyor."
	feedback_time = 4.0

func refresh_ui() -> void:
	if input_kind == "camera" and diagnostic_label:
		var live: String = bridge.diagnostic_status if clock - bridge.last_diagnostic < 2.0 else "Kamera bağlantısı / model hazırlanıyor…"
		var result: String = bridge.diagnostic_result if clock - bridge.last_diagnostic < 2.0 else ""
		diagnostic_label.text = live + "\n" + result + "\nF8: rapor   ·   F9: yerel görsel kayıt " + ("AÇIK" if bridge.recording else "KAPALI") + "   ·   F10: yeniden hazırlan"
	if title == null:
		return
	title.text = "KAT %02d / %02d   /   KÜL MABEDİ" % [encounter.floor_number, Encounter.SESSION_FLOORS]
	counters.text = "Kül Muhafızı     ·     Skor %d     ·     Seri %d     ·     En iyi seri %d" % [encounter.score, encounter.combo, encounter.best_combo]
	health_bar.max_value = encounter.max_health
	health_bar.value = encounter.health
	health_bar.visible = encounter.phase == "fight"
	timer_bar.visible = encounter.timed and encounter.phase == "fight"
	var display_time = encounter.pause_at if encounter.paused else clock
	timer_bar.value = clampf((encounter.deadline - display_time) / encounter.window_seconds(), 0, 1) * 100
	seal.visible = encounter.phase == "fight"
	var first_result = encounter.phase == "results" and not result_panel.visible
	result_panel.visible = encounter.phase == "results"
	if result_panel.visible:
		if first_result:
			if bridge:
				bridge.sync(encounter)
			save_result()
		result_title.text = "ÜÇ MÜHÜR KIRILDI" if encounter.completed else "TIRMANIŞ SONA ERDİ"
		result_stats.text = "Skor %d     ·     Ulaşılan kat %d / %d\nEn iyi seri %d" % [encounter.score, encounter.floor_number, Encounter.SESSION_FLOORS, encounter.best_combo]
		var record: Dictionary = progress_store.records[input_kind]
		result_record.text = "BU KAYNAĞIN YEREL REKORLARI\nSkor %d  ·  Kat %d  ·  Seri %d\nSeans %d  ·  Tamamlanan %d" % [record.best_score, record.highest_floor, record.best_combo, record.sessions, record.completed]
		result_status.text = progress_store.status if save_enabled else "Kontrol çalıştırması · ilerleme kaydı kapalı."
		prompt.text = "YENİ BİR TIRMANIŞ"
		help.text = "R: yeni üç katlık seans     ·     Esc: çıkış"
		feedback.text = ""
		return
	if encounter.paused:
		prompt.text = "DURAKLATILDI"
		help.text = "P: devam et     ·     R: demoyu sıfırla     ·     Esc: çıkış"
		if bridge:
			prompt.text = "DURAKLATILDI · " + ("BAĞLANTI HAZIR" if bridge.connected and bridge.source_ready else "GİRDİ BEKLENİYOR")
			feedback.text = bridge.status
			if input_kind == "camera":
				if bridge.manual_paused:
					prompt.text = "ELLE DURAKLATILDI"
					help.text = "P: otomatik devamı etkinleştir"
				elif bridge.source_ready:
					prompt.text = "ELLERİN GÖRÜNSÜN"
					help.text = "Ellerini kısa bir an sabit tut; hazır olunca otomatik başlar."
				else:
					prompt.text = "KAMERA TAKİBİ BEKLENİYOR"
					help.text = "Kamera ve hazırlık otomatik. Kadraja yerleşip ellerini rahatça sabit tut."
				help.text += "\nP: elle duraklat     ·     Esc: çıkış"
	elif encounter.phase == "approach":
		prompt.text = "MUHAFIZA YAKLAŞ"
		help.text = "W / ↑: ilerle     ·     S / ↓: geri     ·     A / D: yana adım\nP: duraklat     ·     R: sıfırla     ·     Esc: çıkış"
		if input_kind == "camera":
			help.text = "Ellerin görünür olsun; muhafıza otomatik yaklaşılıyor.\nP: elle duraklat     ·     Esc: çıkış"
	elif encounter.phase == "fight":
		prompt.text = "MÜHRÜ KIR   /   " + NAMES[encounter.requested()]
		help.text = "1: Sol yumruk     ·     2: Sağ yumruk     ·     3: Aşağıdan vur\nP: duraklat     ·     R: sıfırla     ·     Esc: çıkış"
		if bridge:
			help.text = ("Python sentetik olayları · Kamera kapalı" if bridge.source == "synthetic" else "Süre sınırı yok · Sol / sağ yumruk veya aşağıdan yukarı vur.") + "\nP: duraklat     ·     R: sıfırla     ·     Esc: çıkış"
	else:
		prompt.text = "BİR ÜST KATA ÇIK"
		help.text = "W / ↑ ile açılan merdivene ilerle; yakında E ile tırman.\nKaranlığın üstüne yürü."
		if input_kind == "camera":
			help.text = "Ellerini kısa bir an sabit tut; merdiven ve yeni kat otomatik.\nP: elle duraklat     ·     Esc: çıkış"
	help.text += "     ·     F: seansı bitir"
