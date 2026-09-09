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

func pulse(b, ready: bool = true) -> Dictionary:
	return {"v": 1, "type": "pulse", "source": "synthetic", "client": b.client,
		"link": b.link, "lease": b.lease_id, "ready": ready}

func hit(b, e, id: int, move: String) -> Dictionary:
	return {"v": 1, "type": "hit", "source": "synthetic", "client": b.client,
		"link": b.link, "lease": b.lease_id, "event": id,
		"encounter": b.session + ":" + str(e.floor_number), "prompt": str(b.revision),
		"move": move, "age_ms": 0}

func _initialize() -> void:
	var e = Encounter.new()
	var b = Bridge.new()
	check(b.start("synthetic", 0) == OK, "Loopback bind succeeds")
	var occupied = Bridge.new()
	check(occupied.start("synthetic", b.socket.get_local_port()) != OK, "Occupied port fails safely")
	occupied.close()
	b.poll(e, 0.0)
	check(e.paused, "Missing producer pauses")
	var hello = {"v": 1, "type": "hello", "source": "synthetic", "client": "a".repeat(32)}
	b.receive(hello, 34561, e, 0.01)
	check(not b.connected and b.peer_port == 34561, "Hello alone cannot mark source ready")
	b.receive(pulse(b), 34562, e, 0.02)
	check(not b.connected, "Other local port rejected")
	b.receive(pulse(b), 34561, e, 0.03)
	check(b.connected and b.source_ready and e.paused, "Handshake requires explicit resume")
	e.set_paused(false, 0.04)
	e.begin(0.04)
	b.sync(e)
	b.publish(e, 0.04)
	var wrong = hit(b, e, 1, "right_punch")
	b.receive(wrong, 34561, e, 0.05)
	check(e.health == 4 and b.accepted_id == 1, "Observed wrong class does not become requested class")
	var first = hit(b, e, 2, "left_punch")
	b.receive(first, 34561, e, 0.06)
	check(e.health == 3, "Fresh numeric event damages once")
	b.receive(first, 34561, e, 0.07)
	check(e.health == 3 and b.accepted_id == 2, "Duplicate rejected")
	b.publish(e, 0.08)
	var old_prompt = first.duplicate()
	old_prompt.event = 3
	old_prompt.move = "right_punch"
	old_prompt.lease = b.lease_id
	b.receive(old_prompt, 34561, e, 0.09)
	check(e.health == 3, "Old prompt cannot hit a new target even with fresh lease")
	var stale = hit(b, e, 4, "right_punch")
	b.receive(stale, 34561, e, 0.60)
	check(e.health == 3, "Expired server lease rejected without clock sync")
	b.publish(e, 0.61)
	var old_detection = hit(b, e, 5, "right_punch")
	old_detection.age_ms = 251
	b.receive(old_detection, 34561, e, 0.62)
	check(e.health == 3, "Stale detection rejected")
	var malformed = hit(b, e, 6, "right_punch")
	malformed.event = true
	b.receive(malformed, 34561, e, 0.63)
	malformed.event = 6
	malformed.image = "forbidden"
	b.receive(malformed, 34561, e, 0.64)
	malformed.erase("image")
	malformed.source = "camera"
	b.receive(malformed, 34561, e, 0.65)
	check(e.health == 3 and b.last_event == 5, "Bad field types, extra payload and mixed source rejected")
	var before_pause = hit(b, e, 7, "right_punch")
	b.receive(pulse(b, false), 34561, e, 0.66)
	check(e.paused and not b.source_ready, "Unready tracking pauses immediately")
	b.publish(e, 0.67)
	b.receive(pulse(b), 34561, e, 0.68)
	check(e.paused and b.source_ready, "Tracking recovery never auto-resumes")
	e.set_paused(false, 0.69)
	b.sync(e)
	b.receive(before_pause, 34561, e, 0.70)
	check(e.health == 3, "Events from before pause cannot damage after resume")
	var prior_link = b.link
	b.poll(e, 1.70)
	check(e.paused and not b.connected, "Heartbeat loss pauses encounter")
	b.receive(hello, 34561, e, 1.71)
	check(b.link != prior_link, "Reconnect rotates link even for same producer")
	b.receive(pulse(b), 34561, e, 1.72)
	e.set_paused(false, 1.73)
	b.sync(e)
	b.publish(e, 1.73)
	var previous_connection = hit(b, e, 8, "right_punch")
	previous_connection.link = prior_link
	b.receive(previous_connection, 34561, e, 1.74)
	check(e.health == 3, "Previous connection cannot inject a fresh-looking event")
	b.receive(hit(b, e, 1, "right_punch"), 34561, e, 1.75)
	check(e.health == 2, "New producer event counter starts safely")
	b.publish(e, 1.76)
	var timed_out = hit(b, e, 2, "uppercut")
	e.advance(e.deadline + 0.01)
	b.sync(e)
	b.receive(timed_out, 34561, e, e.last_now)
	check(e.health == 2, "Deadline change invalidates prior prompt")
	var floor_now: float = e.last_now + 0.1
	# Complete remaining health through fresh contexts, then replay across a floor.
	for id in [3, 4]:
		b.publish(e, floor_now)
		b.receive(hit(b, e, id, e.requested()), 34561, e, floor_now)
		floor_now += 0.01
	var old_floor = hit(b, e, 5, "right_punch")
	e.climb(floor_now)
	e.begin(floor_now)
	b.sync(e)
	b.publish(e, floor_now)
	old_floor.lease = b.lease_id
	old_floor.prompt = str(b.revision)
	b.receive(old_floor, 34561, e, floor_now + 0.01)
	check(e.floor_number == 2 and e.health == e.max_health, "Previous encounter cannot score on new floor")
	b.publish(e, floor_now + 0.02)
	var before_results = hit(b, e, 6, e.requested())
	e.finish(floor_now + 0.03)
	b.sync(e)
	b.receive(before_results, 34561, e, floor_now + 0.04)
	check(e.phase == "results" and e.health == e.max_health and b.leases.is_empty(), "Results revoke leases and reject pending hits")
	b.drop(e, floor_now + 0.05)
	check(not e.paused and e.phase == "results", "Disconnected producer cannot hide results behind pause")
	var old_session = b.session
	var restarted = Encounter.new()
	b.restart(restarted, floor_now + 0.06)
	check(b.session != old_session and restarted.paused and b.peer_port == 0, "Restart rotates session and requires new handshake")
	b.receive(hello, 34561, restarted, floor_now + 0.07)
	b.receive(pulse(b), 34561, restarted, floor_now + 0.08)
	restarted.set_paused(false, floor_now + 0.09)
	restarted.begin(floor_now + 0.09)
	b.sync(restarted)
	b.publish(restarted, floor_now + 0.09)
	b.receive(before_results, 34561, restarted, floor_now + 0.10)
	var relabelled = hit(b, restarted, 7, "left_punch")
	relabelled.encounter = old_session + ":1"
	b.receive(relabelled, 34561, restarted, floor_now + 0.11)
	check(restarted.health == 4, "Prior session rejected even on same floor with fresh link and lease")
	b.receive(hit(b, restarted, 8, "left_punch"), 34561, restarted, floor_now + 0.12)
	check(restarted.health == 3, "New session accepts fresh event after explicit resume")
	b.close()
	print("Event bridge checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
