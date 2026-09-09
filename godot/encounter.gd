extends RefCounted
## Authoritative local encounter state. No rendering, camera or clock dependency.

const MOVES = ["left_punch", "right_punch", "uppercut"]
const SESSION_FLOORS = 3
var completed: bool = false
var floor_number: int = 1
var phase: String = "approach"
var health: int = 4
var max_health: int = 4
var score: int = 0
var combo: int = 0
var best_combo: int = 0
var step: int = 0
var deadline: float = 0.0
var timed: bool = true
var paused: bool = false
var pause_at: float = 0.0
var used_events: Dictionary = {}
var last_now: float = 0.0

func requested() -> String:
	return MOVES[(step + floor_number - 1) % MOVES.size()]

func window_seconds() -> float:
	return maxf(1.8, 4.0 - (floor_number - 1) * 0.15)

func begin(now: float) -> bool:
	if phase != "approach" or paused or now < last_now:
		return false
	last_now = now
	phase = "fight"
	deadline = now + window_seconds()
	return true

func advance(now: float) -> bool:
	if paused or now < last_now:
		return false
	last_now = now
	if timed and phase == "fight" and now > deadline:
		combo = 0
		step += 1
		deadline = now + window_seconds()
		return true
	return false

func strike(move: String, event_id: int, now: float) -> String:
	if paused or phase != "fight" or now < last_now:
		return "inactive"
	if used_events.has(event_id):
		return "duplicate"
	used_events[event_id] = true
	if advance(now):
		return "late"
	if move != requested():
		combo = 0
		return "wrong"
	health -= 1
	combo += 1
	best_combo = maxi(best_combo, combo)
	score += 100 + mini(combo - 1, 9) * 20
	step += 1
	deadline = now + window_seconds()
	if health == 0:
		if floor_number == SESSION_FLOORS:
			finish(now, true)
		else:
			phase = "cleared"
		return "defeated"
	return "hit"

func finish(now: float, success: bool = false) -> bool:
	if phase == "results" or now < last_now:
		return false
	last_now = now
	completed = success and floor_number == SESSION_FLOORS and health == 0
	phase = "results"
	paused = false
	return true

func summary() -> Dictionary:
	return {"score": score, "highest_floor": floor_number,
		"best_combo": best_combo, "completed": completed}

func climb(now: float) -> bool:
	if phase != "cleared" or paused or now < last_now:
		return false
	last_now = now
	floor_number += 1
	max_health = mini(4 + (floor_number - 1) / 2, 8)
	health = max_health
	step = 0
	phase = "approach"
	# IDs are globally unique in the input adapter; retain them across floors.
	return true

func set_paused(value: bool, now: float) -> void:
	if phase == "results" or value == paused or now < last_now:
		return
	last_now = now
	if value:
		pause_at = now
	else:
		deadline += now - pause_at
	paused = value
