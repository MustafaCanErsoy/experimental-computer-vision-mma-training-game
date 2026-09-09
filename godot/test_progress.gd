extends SceneTree
const Store = preload("res://progress_store.gd")
const Encounter = preload("res://encounter.gd")
var checks: int = 0
var failures: int = 0

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		push_error(message)
		failures += 1

func write(path: String, content: String) -> void:
	var file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string(content)
	file.close()

func _initialize() -> void:
	var temporary = DirAccess.create_temp("shadowmma-progress-test")
	var path = temporary.get_current_dir()
	var store = Store.new(path)
	check(store.generation == 0 and store.records.camera.sessions == 0, "Missing records start empty")
	var e = Encounter.new()
	var id = 0
	for index in range(3):
		e.begin(0.0)
		while e.phase == "fight":
			id += 1
			e.strike(e.requested(), id, 0.0)
		if index < 2:
			check(e.phase == "cleared" and e.climb(0.0), "Intermediate victory allows next floor")
	check(e.phase == "results" and e.completed and e.score == 2740 and e.best_combo == 13, "Third victory ends bounded session")
	var result = e.summary()
	e.advance(90.0)
	e.set_paused(true, 90.0)
	check(not e.climb(90.0) and not e.begin(90.0) and not e.finish(90.0) and not e.paused, "Results cannot climb, fight, finish twice or pause")
	check(e.strike("left_punch", 90, 90.0) == "inactive" and e.summary() == result, "Results freeze score and summary")
	check(store.record("keyboard", result), "First completed summary saved")
	check(Store.new(path).records.keyboard.best_score == 2740, "Fresh store reloads persistent record")
	check(store.record("synthetic", {"score": 100, "highest_floor": 1, "best_combo": 1, "completed": false}), "Synthetic summary saved separately")
	check(store.record("camera", {"score": 0, "highest_floor": 1, "best_combo": 0, "completed": false}), "Camera record has independent bucket")
	store = Store.new(path)
	check(store.generation == 3 and store.records.keyboard.sessions == 1 and store.records.synthetic.best_score == 100 and store.records.camera.best_score == 0, "Atomic replacement keeps source records apart")
	check(not store.record("other", result) and not store.record("camera", {"score": true, "highest_floor": 1, "best_combo": 0, "completed": false}), "Unknown sources and invalid numeric types rejected")
	write(path.path_join("progress-0.json"), "{broken")
	store = Store.new(path)
	check(store.generation == 2 and store.records.keyboard.best_score == 2740 and store.records.camera.sessions == 0, "Corrupt newest slot falls back to previous complete generation")
	write(path.path_join("progress-1.json.tmp"), "{partial")
	check(Store.new(path).generation == 2, "Interrupted temporary write cannot replace committed state")
	check(store.record("camera", result) and Store.new(path).records.camera.best_score == 2740, "Recovered store can commit again")
	write(path.path_join("progress-0.json"), '{"version":2}')
	store = Store.new(path)
	check(not store.writable and not store.record("keyboard", result), "Future schema preserved without overwriting")
	check(FileAccess.get_file_as_string(path.path_join("progress-0.json")) == '{"version":2}', "Future version bytes unchanged")
	write(path.path_join("progress-0.json"), "null")
	write(path.path_join("progress-1.json"), "[]")
	store = Store.new(path)
	check(store.generation == 0 and store.writable and store.records.keyboard.sessions == 0, "Two corrupt files recover to empty state")
	check(store.record("keyboard", result), "Both corrupt slots can recover through a new valid save")
	# Block the next rename with a directory; the existing generation must survive.
	DirAccess.remove_absolute(path.path_join("progress-1.json"))
	DirAccess.make_dir_absolute(path.path_join("progress-1.json"))
	check(not store.record("keyboard", result) and store.generation == 1 and store.records.keyboard.sessions == 1, "Failed replacement does not increment memory record")
	check(Store.new(path).records.keyboard.sessions == 1, "Failed replacement preserves committed generation")
	DirAccess.remove_absolute(path.path_join("progress-1.json"))
	check(store.record("keyboard", result) and Store.new(path).records.keyboard.sessions == 2, "Retry records failed result exactly once")
	DirAccess.make_dir_absolute(path.path_join("progress-0.json.tmp"))
	check(not store.record("keyboard", result) and Store.new(path).records.keyboard.sessions == 2, "Temporary open failure preserves previous record")
	DirAccess.remove_absolute(path.path_join("progress-0.json.tmp"))
	var invalid = {"version": 1, "generation": 3, "records": store.records.duplicate(true)}
	invalid.records.camera.best_score = -1
	check(not store.valid(invalid), "Negative persisted metrics rejected")
	invalid.records.camera.best_score = 0
	invalid.records.camera.highest_floor = 4
	check(not store.valid(invalid), "Out-of-session floor in saved data rejected")
	var stopped = Encounter.new()
	stopped.begin(1.0)
	stopped.strike("left_punch", 1, 1.1)
	stopped.set_paused(true, 1.2)
	check(stopped.finish(2.0) and not stopped.completed and stopped.summary().score == 100 and not stopped.paused, "Early finish from pause retains partial result")
	print("Progress/session checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
