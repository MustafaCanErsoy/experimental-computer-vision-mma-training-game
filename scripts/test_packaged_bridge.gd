extends SceneTree
var scene
var temporary
var received: int = 0

func _initialize() -> void:
	setup.call_deferred()

func setup() -> void:
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	temporary = DirAccess.create_temp("shadowmma-package-test")
	scene.progress_store = load("res://progress_store.gd").new(temporary.get_current_dir())
	scene.bridge.strike_received.connect(func(_move, _outcome): received += 1)
	scene.camera.position.z = 2.6
	process_frame.connect(check_frame)

func check_frame() -> void:
	if Time.get_ticks_msec() > 12000:
		push_error("Packaged producer handshake/hit timeout")
		quit(1)
		return
	if scene.encounter.paused and scene.bridge.connected and scene.bridge.source_ready:
		var event = InputEventKey.new()
		event.pressed = true
		event.keycode = KEY_P
		scene._unhandled_key_input(event)
	if received > 0 and scene.encounter.health < 4:
		print("PACKAGED_BRIDGE_OK")
		quit(0)
