extends SceneTree

const Encounter = preload("res://encounter.gd")
var failures: int = 0
var checks: int = 0

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		push_error(label)
		failures += 1

func _initialize() -> void:
	var e = Encounter.new()
	check(not e.climb(0.0), "Cannot climb before defeating guardian")
	check(e.strike("left_punch", 1, 0.0) == "inactive", "No hit before encounter")
	check(e.begin(0.0), "Encounter starts")
	check(e.strike("right_punch", 2, 0.1) == "wrong" and e.health == 4, "Wrong move does no damage")
	check(e.strike("left_punch", 3, 0.2) == "hit", "Requested hit damages")
	check(e.strike("right_punch", 3, 0.3) == "duplicate" and e.health == 3, "Duplicate does no damage")
	e.set_paused(true, 0.4)
	check(e.strike("right_punch", 4, 10.0) == "inactive", "Pause blocks hits")
	e.set_paused(false, 10.4)
	check(e.strike("right_punch", 4, 10.5) == "hit", "Pause preserves remaining time")
	check(e.strike("uppercut", 5, 15.0) == "late", "Late hit is not applied to next prompt")
	check(e.combo == 0 and e.health == 2, "Timeout resets combo without damage")
	check(e.strike(e.requested(), 6, 15.1) == "hit", "Next prompt remains usable")
	check(e.strike(e.requested(), 7, 15.2) == "defeated", "Guardian defeated")
	check(e.strike("left_punch", 8, 15.3) == "inactive", "Dead guardian cannot be hit")
	check(e.climb(16.0) and e.floor_number == 2 and e.phase == "approach", "Stairs advance exactly one floor")
	check(not e.climb(16.1), "Cannot skip new encounter")
	e.begin(17.0)
	check(e.strike(e.requested(), 3, 17.1) == "duplicate", "Old event cannot damage new floor")
	check(e.strike(e.requested(), 9, 16.5) == "inactive", "Out-of-order event rejected")
	var practice = Encounter.new()
	practice.timed = false
	practice.begin(0.0)
	check(not practice.advance(3600.0) and practice.requested() == "left_punch", "Untimed target survives one hour without expiring")
	check(practice.strike("left_punch", 1, 3600.1) == "hit", "Untimed target accepts delayed completed movement")
	check(not practice.advance(7200.0) and practice.combo == 1 and practice.requested() == "right_punch", "Time alone does not reset combo or change next target")
	print("Encounter checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
