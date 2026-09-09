extends SceneTree
const Bridge = preload("res://event_bridge.gd")
const Encounter = preload("res://encounter.gd")
var checks: int = 0
var failures: int = 0

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func packet(b, kind: String) -> Dictionary:
	return {"v": 1, "type": kind, "source": b.source, "client": b.client, "link": b.link, "lease": b.lease_id}

func pulse(b, ready: bool = true) -> Dictionary:
	var p = packet(b, "pulse")
	p.ready = ready
	return p

func guard(b, id: int, held: bool = true) -> Dictionary:
	var p = packet(b, "guard")
	p.event = id
	p.held = held
	return p

func _initialize() -> void:
	var b = Bridge.new()
	var e = Encounter.new()
	b.start("camera", 0)
	b.poll(e, 0.0)
	var hello = {"v": 1, "type": "hello", "source": "camera", "client": "c".repeat(32)}
	b.receive(hello, 34001, e, 0.01)
	b.receive(guard(b, 1), 34001, e, 0.02)
	check(e.paused, "Guard cannot bypass unready source")
	b.receive(pulse(b), 34001, e, 0.03)
	check(e.paused, "Visible calibrated camera alone does not resume")
	var diagnostic = packet(b, "diagnostic")
	diagnostic.status = "Hazırlık %80"
	diagnostic.result = "Sayılmadı: iki kare yok"
	diagnostic.recording = true
	b.receive(diagnostic, 34001, e, 0.031)
	check(b.diagnostic_status == "Hazırlık %80" and b.recording and e.paused, "Diagnostic status never resumes gameplay")
	var bad_diagnostic = diagnostic.duplicate()
	bad_diagnostic.recording = "true"
	b.receive(bad_diagnostic, 34001, e, 0.032)
	check(b.last_diagnostic == 0.031, "Malformed diagnostic cannot change live status")
	b.receive(guard(b, 2, false), 34001, e, 0.04)
	check(e.paused, "No stable guard means wait")
	var invalid = guard(b, 3)
	invalid.held = 1
	b.receive(invalid, 34001, e, 0.05)
	check(e.paused, "Malformed guard rejected")
	var before_resume = b.lease_id
	b.receive(guard(b, 3), 34001, e, 0.06)
	check(not e.paused and b.has_guard(0.06), "Stable camera guard automatically resumes")
	check(not b.valid_lease(before_resume, 0.06), "Auto resume revokes pre-resume hit contexts")
	check(not b.has_guard(0.32), "Old guard expires for camera navigation")
	b.publish(e, 0.07)
	b.receive(guard(b, 4, false), 34001, e, 0.08)
	check(not e.paused and not b.has_guard(0.08), "Leaving guard to punch does not pause")
	b.receive(guard(b, 3), 34001, e, 0.09)
	check(not b.has_guard(0.09), "Reordered guard cannot override latest release")
	b.receive(pulse(b, false), 34001, e, 0.10)
	check(e.paused, "Lost tracking still pauses immediately")
	b.publish(e, 0.11)
	b.receive(pulse(b), 34001, e, 0.12)
	check(e.paused, "Tracking recovery without guard waits")
	var expired = guard(b, 5)
	b.receive(expired, 34001, e, 0.62)
	check(e.paused, "Expired lease cannot resume")
	b.publish(e, 0.63)
	b.receive(pulse(b), 34001, e, 0.64)
	b.receive(guard(b, 6), 34001, e, 0.65)
	check(not e.paused, "Returning to guard resumes without keyboard")
	b.toggle_camera_pause(e, 0.66)
	b.publish(e, 0.67)
	b.receive(guard(b, 7), 34001, e, 0.68)
	check(e.paused and b.manual_paused, "Manual P pause stays latched despite guard")
	b.drop(e, 0.69)
	b.receive(hello, 34001, e, 0.70)
	b.receive(pulse(b), 34001, e, 0.71)
	b.receive(guard(b, 1), 34001, e, 0.72)
	check(e.paused and b.manual_paused, "Disconnect cannot clear intentional manual pause")
	b.toggle_camera_pause(e, 0.73)
	b.publish(e, 0.74)
	b.receive(guard(b, 2), 34001, e, 0.75)
	check(not e.paused, "P re-enables guard auto resume")
	e.finish(0.76)
	b.sync(e)
	b.publish(e, 0.77)
	b.receive(guard(b, 3), 34001, e, 0.78)
	check(e.phase == "results", "Guard never restarts results")
	var prior = guard(b, 4)
	e = Encounter.new()
	b.restart(e, 0.79)
	b.receive(prior, 34001, e, 0.80)
	check(e.paused and not b.has_guard(0.80), "Restart rejects previous session guard")
	b.close()
	b = Bridge.new()
	e = Encounter.new()
	b.start("synthetic", 0)
	b.poll(e, 0.0)
	hello.source = "synthetic"
	b.receive(hello, 34001, e, 0.01)
	b.receive(pulse(b), 34001, e, 0.02)
	b.receive(guard(b, 1), 34001, e, 0.03)
	check(e.paused, "Synthetic still requires P and cannot use camera guard")
	b.close()
	print("Guard resume checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
