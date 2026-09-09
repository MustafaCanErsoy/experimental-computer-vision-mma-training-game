extends SceneTree
var scene
var stage: String = "CALIBRATION"
var stage_at: float = 0.0
var checks: int = 0
var failures: int = 0
var first_prompt: int = 0
var saw_guard_release: bool = false

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func transition(next: String) -> void:
	stage = next
	stage_at = Time.get_ticks_msec() / 1000.0
	print("CAMERA_READY_STAGE:", stage)

func key_p() -> void:
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_P
	scene._unhandled_key_input(event)

func _initialize() -> void:
	setup.call_deferred()

func setup() -> void:
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	scene.save_enabled = false
	check(scene.encounter.paused, "Uncalibrated camera waits without keyboard")
	process_frame.connect(check_frame)

func check_frame() -> void:
	var now = Time.get_ticks_msec() / 1000.0
	if now > 40.0:
		push_error("Camera readiness test timeout at " + stage)
		quit(1)
		return
	if stage == "CALIBRATION" and not scene.encounter.paused:
		check(scene.bridge.has_guard(now), "Calibrated stable guard resumes without P")
		check(scene.bridge.last_diagnostic >= 0, "Automatic worker publishes live diagnostics")
		transition("RUNNING")
	elif stage == "RUNNING":
		if scene.encounter.paused:
			check(false, "Fresh queued frame must not transiently pause game after delayed Tk callback")
			quit(1)
		elif now - stage_at > 1.4:
			check(true, "Game stayed running through delayed camera GUI callbacks")
			transition("LOSE_TRACKING")
	elif stage == "LOSE_TRACKING" and not scene.bridge.source_ready:
		check(scene.encounter.paused, "Real invalid tracking pauses")
		scene.refresh_ui()
		check(scene.prompt.text == "KAMERA TAKİBİ BEKLENİYOR", "Missing torso shows tracking status instead of guard demand")
		transition("RECOVER")
	elif stage == "RECOVER" and not scene.encounter.paused:
		check(scene.bridge.has_guard(now), "Guard recovery automatically resumes")
		transition("APPROACH")
	elif stage == "APPROACH" and scene.encounter.phase == "fight":
		check(is_equal_approx(scene.camera.position.z, 2.6), "Camera approaches guardian without W")
		first_prompt = scene.encounter.step
		check(scene.encounter.requested() == "left_punch", "First camera target requests left punch")
		scene.refresh_ui()
		check(not scene.encounter.timed and not scene.timer_bar.visible, "Camera practice has no countdown")
		transition("WAIT_WITHOUT_TIMER")
	elif stage == "WAIT_WITHOUT_TIMER" and now - stage_at > 4.5:
		check(scene.encounter.step == first_prompt and scene.encounter.score == 0, "Waiting beyond old deadline keeps same camera target")
		transition("LEFT_PUNCH")
	elif stage == "LEFT_PUNCH":
		if scene.encounter.paused or not scene.bridge.source_ready:
			check(false, "Visible torso keeps fight running through left punch and hand occlusion")
			quit(1)
		elif scene.encounter.score == 0:
			saw_guard_release = saw_guard_release or not scene.bridge.has_guard(now)
			if scene.encounter.step != first_prompt:
				check(false, "Jab must score before target changes")
				quit(1)
		else:
			check(saw_guard_release, "Punch left guard without returning to guard screen")
			check(scene.encounter.score == 100 and scene.encounter.health == 3, "Observed left punch and visible return score once through real Detector and UDP")
			transition("LEFT_PUNCH_COMPLETE")
	elif stage == "LEFT_PUNCH_COMPLETE" and now - stage_at > 0.5:
		check(scene.encounter.score == 100 and scene.encounter.step == first_prompt + 1, "Holding guard cannot duplicate left punch")
		transition("RIGHT_PUNCH")
	elif stage == "RIGHT_PUNCH" and scene.encounter.score > 100:
		check(scene.encounter.score == 220 and scene.encounter.requested() == "uppercut", "Right punch scores and requests upward motion")
		transition("UPPERCUT")
	elif stage == "UPPERCUT" and scene.encounter.score > 220:
		check(scene.encounter.score == 360 and scene.encounter.health == 1, "Upward motion scores through actual detector and UDP")
		transition("THREE_COMPLETE")
	elif stage == "THREE_COMPLETE" and now - stage_at > 1.0:
		check(scene.encounter.score == 360, "Release after third move cannot duplicate score")
		key_p()
		transition("MANUAL_PAUSE")
	elif stage == "MANUAL_PAUSE" and now - stage_at > 0.5:
		check(scene.encounter.paused and scene.bridge.manual_paused, "Intentional manual pause remains held")
		key_p()
		transition("MANUAL_RELEASE")
	elif stage == "MANUAL_RELEASE" and not scene.encounter.paused:
		check(scene.bridge.has_guard(now), "Manual release enables hands-free guard resume")
		# Seed victory to test navigation independently of punch classification.
		for i in range(scene.encounter.health):
			var move = scene.encounter.requested()
			var outcome = scene.encounter.strike(move, 100 + i, scene.clock)
			scene.show_strike(move, outcome)
		transition("STAIRS")
	elif stage == "STAIRS" and scene.encounter.floor_number == 2:
		check(scene.guardian.visible, "Camera climbs stairs and rebuilds next floor without E")
		transition("SECOND_APPROACH")
	elif stage == "SECOND_APPROACH" and scene.encounter.phase == "fight":
		check(not scene.encounter.paused, "Second floor fight starts without keyboard")
		scene.encounter.finish(scene.clock)
		transition("RESULTS")
	elif stage == "RESULTS" and now - stage_at > 0.4:
		check(scene.encounter.phase == "results", "Holding guard cannot restart results")
		var event = InputEventKey.new()
		event.pressed = true
		event.keycode = KEY_F9
		scene._unhandled_key_input(event)
		transition("RECORDING_OFF")
	elif stage == "RECORDING_OFF" and not scene.bridge.recording:
		check(true, "F9 disables optional frame recording through real control channel")
		scene.restart_session()
		check(not scene.encounter.timed, "Restart preserves untimed camera practice")
		print("Camera readiness live checks: ", checks, "; failures: ", failures)
		quit(1 if failures else 0)
