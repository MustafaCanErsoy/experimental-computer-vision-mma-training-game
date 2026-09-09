extends SceneTree
## Exercises the actual scene and keyboard adapter without a camera or OS input.
var failures: int = 0
var checks: int = 0

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		push_error(message)
		failures += 1

func key(scene: Node, code: Key) -> void:
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = code
	scene._unhandled_key_input(event)

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	var temporary = DirAccess.create_temp("shadowmma-tower-test")
	scene.progress_store = preload("res://progress_store.gd").new(temporary.get_current_dir())
	scene.set_process(false)
	check(scene.encounter.phase == "approach" and scene.guardian.visible, "Guardian awaits approach")
	key(scene, KEY_E)
	check(scene.encounter.floor_number == 1, "Stairs initially locked")
	scene.camera.position.z = 2.6
	scene._process(0.01)
	check(scene.encounter.phase == "fight" and scene.seal.visible, "Approach starts encounter")
	key(scene, KEY_P)
	var timer = scene.timer_bar.value
	scene._process(10.0)
	check(scene.timer_bar.value == timer, "Pause freezes displayed time")
	key(scene, KEY_1)
	check(scene.encounter.health == 4, "Paused keyboard does no damage")
	key(scene, KEY_P)
	for code in [KEY_1, KEY_2, KEY_3, KEY_1]:
		key(scene, code)
	check(scene.encounter.phase == "cleared" and not scene.guardian.visible and scene.shards.size() == 24, "Four requested hits shatter guardian")
	key(scene, KEY_E)
	check(scene.encounter.floor_number == 1, "Climb requires reaching stairs")
	scene.camera.position.z = -6.0
	key(scene, KEY_E)
	check(scene.encounter.floor_number == 2 and scene.guardian.visible and scene.shards.is_empty(), "Stairs reset next floor")
	check(is_equal_approx(scene.camera.position.z, 7.2) and scene.encounter.score == 520, "New floor keeps score and restores entrance")
	for floor_index in range(2):
		scene.camera.position.z = 2.6
		scene._process(0.01)
		while scene.encounter.phase == "fight":
			key(scene, [KEY_1, KEY_2, KEY_3, KEY_1][scene.encounter.MOVES.find(scene.encounter.requested())])
		if scene.encounter.phase == "cleared":
			scene.camera.position.z = -6.0
			key(scene, KEY_E)
	check(scene.encounter.completed and scene.result_panel.visible and scene.result_saved, "Third guardian shows and saves results")
	check(scene.result_stats.text.contains("2740") and scene.progress_store.records.keyboard.sessions == 1, "Result screen uses authoritative score")
	for code in [KEY_1, KEY_E, KEY_P, KEY_F, KEY_K]:
		key(scene, code)
	scene._process(100.0)
	check(scene.encounter.phase == "results" and scene.encounter.score == 2740 and scene.progress_store.records.keyboard.sessions == 1, "Results block gameplay and duplicate saves")
	key(scene, KEY_R)
	check(scene.encounter.floor_number == 1 and scene.encounter.score == 0 and not scene.result_panel.visible and scene.guardian.visible, "Restart restores clean first encounter")
	scene.camera.position.z = 2.6
	scene._process(0.01)
	key(scene, KEY_1)
	key(scene, KEY_P)
	key(scene, KEY_F)
	check(scene.result_panel.visible and not scene.encounter.completed and scene.encounter.score == 100, "F ends paused partial session with result")
	check(scene.progress_store.records.keyboard.sessions == 2 and scene.progress_store.records.keyboard.best_score == 2740 and scene.progress_store.records.camera.sessions == 0, "Partial run preserves best and leaves camera records empty")
	key(scene, KEY_R)
	var blocked_path = temporary.get_current_dir().path_join("blocked")
	var blocking_file = FileAccess.open(blocked_path, FileAccess.WRITE)
	blocking_file.close()
	scene.progress_store = preload("res://progress_store.gd").new(blocked_path)
	key(scene, KEY_F)
	check(not scene.result_saved and scene.result_status.text.contains("K:"), "Write failure keeps visible result and offers retry")
	scene._process(1.0)
	key(scene, KEY_K)
	check(scene.progress_store.generation == 0 and scene.result_panel.visible, "Repeated failure neither counts nor loses result")
	DirAccess.remove_absolute(blocked_path)
	key(scene, KEY_K)
	key(scene, KEY_K)
	check(scene.result_saved and scene.progress_store.records.keyboard.sessions == 1, "K retries successfully and cannot double count")
	print("Tower integration checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
