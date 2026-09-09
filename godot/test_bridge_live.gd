extends SceneTree
## Test-only driver: actual tower, actual UDP; Python supplies the movements.
var scene
var checks: int = 0
var failures: int = 0
var outcomes: Array = []
var paused_after_hit: bool = false
var resumed: int = 0
var finished: bool = false
var first_link: String = ""
var checked_first_floor: bool = false
var restarted: bool = false
var temporary

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func key(code: Key) -> void:
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = code
	scene._unhandled_key_input(event)

func _initialize() -> void:
	setup.call_deferred()

func setup() -> void:
	print("Live test: creating tower")
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	temporary = DirAccess.create_temp("shadowmma-live-test")
	scene.progress_store = preload("res://progress_store.gd").new(temporary.get_current_dir())
	print("Live test: tower ready")
	scene.bridge.strike_received.connect(func(move, outcome): outcomes.append([move, outcome]))
	scene.camera.position.z = 2.6
	key(KEY_P)
	check(scene.encounter.paused, "P cannot bypass missing producer")
	process_frame.connect(check_frame)

func check_frame() -> void:
	if scene == null or finished:
		return
	if Time.get_ticks_msec() > 20000:
		push_error("Live bridge test timeout")
		quit(1)
		return
	if scene.encounter.health == 3 and scene.encounter.paused:
		paused_after_hit = true
	if scene.encounter.paused and scene.bridge.connected and scene.bridge.source_ready:
		if first_link.is_empty():
			first_link = scene.bridge.link
		resumed += 1
		print("Live test: resume ", resumed)
		key(KEY_P)
		var health = scene.encounter.health
		key(KEY_1)
		check(scene.encounter.health == health, "Keyboard cannot mix with linked source")
	if scene.encounter.phase == "cleared" and not checked_first_floor:
		checked_first_floor = true
		check(outcomes == [["right_punch", "wrong"], ["left_punch", "hit"], ["right_punch", "hit"], ["uppercut", "hit"], ["left_punch", "defeated"]], "Python classes consumed by real scene")
		check(paused_after_hit and resumed == 2, "Producer loss paused and test explicitly resumed")
		check(first_link != scene.bridge.link, "New Python process identity uses new link")
		check(scene.encounter.score == 520, "Only four correct events scored")
		check(not scene.guardian.visible and scene.shards.size() == 24, "Remote hits animate guardian defeat")
		scene.camera.position.z = -6.0
		key(KEY_E)
		check(scene.encounter.floor_number == 2 and scene.guardian.visible, "Remote victory unlocks actual stairs")
	if scene.encounter.phase == "cleared":
		scene.camera.position.z = -6.0
		key(KEY_E)
	if checked_first_floor and scene.encounter.phase == "approach":
		scene.camera.position.z = 2.6
	if scene.encounter.phase == "results" and not restarted:
		check(scene.encounter.completed and scene.result_panel.visible and scene.result_saved, "Real Python events finish three floors and save result")
		check(scene.progress_store.records.synthetic.best_score == 2740 and scene.progress_store.records.camera.sessions == 0 and scene.progress_store.records.keyboard.sessions == 0, "Linked run saves only synthetic record")
		var prior_session = scene.bridge.session
		key(KEY_R)
		key(KEY_P)
		check(scene.encounter.paused and scene.bridge.session != prior_session, "Restart invalidates session and P cannot bypass fresh handshake")
		restarted = true
	if restarted and scene.encounter.health == 3:
		finished = true
		check(scene.encounter.score == 100 and scene.bridge.session != "" and resumed == 3, "Same Python producer reconnects and scores fresh run after explicit resume")
		check(scene.progress_store.records.synthetic.sessions == 1, "Restart does not duplicate completed record")
		print("Live Python/Godot scene checks: ", checks, "; failures: ", failures)
		quit(1 if failures else 0)
