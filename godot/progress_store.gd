extends RefCounted
## Two generations: replace only the older slot after a complete temporary write.
## Only numeric game summaries are stored; sources never share records.
const VERSION = 1
const SOURCES = ["keyboard", "synthetic", "camera"]
var directory: String
var records: Dictionary = {}
var generation: int = 0
var active_slot: int = -1
var writable: bool = true
var status: String = ""

func _init(path: String = "user://tower_progress") -> void:
	directory = path
	load_records()

func empty_record() -> Dictionary:
	return {"sessions": 0, "completed": 0, "best_score": 0, "highest_floor": 0, "best_combo": 0}

func integer(value, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and value == floor(value) and value >= low and value <= high

func valid(data) -> bool:
	if not data is Dictionary or data.size() != 3:
		return false
	if not integer(data.get("version"), VERSION, VERSION) or not integer(data.get("generation"), 1, 2147483647):
		return false
	if not data.get("records") is Dictionary or data.records.size() != SOURCES.size():
		return false
	for source in SOURCES:
		var row = data.records.get(source)
		if not row is Dictionary or row.size() != 5:
			return false
		for field in ["sessions", "completed", "best_score", "best_combo", "highest_floor"]:
			if not integer(row.get(field), 0, 1000000000):
				return false
		if row.completed > row.sessions or row.highest_floor > 3 or row.best_combo > 13 or row.best_score > 2740:
			return false
	return true

func load_records() -> void:
	for source in SOURCES:
		records[source] = empty_record()
	var damaged = false
	for slot in range(2):
		var path = directory.path_join("progress-%d.json" % slot)
		if not FileAccess.file_exists(path):
			continue
		var file = FileAccess.open(path, FileAccess.READ)
		if file == null:
			writable = false
			continue
		var data = null
		if file.get_length() <= 16384:
			var parser = JSON.new()
			if parser.parse(file.get_as_text()) == OK:
				data = parser.data
		file.close()
		# A newer format belongs to a newer build. Preserve it even if another slot works.
		if data is Dictionary and integer(data.get("version"), VERSION + 1, 2147483647):
			writable = false
		if not valid(data):
			damaged = true
			continue
		if data.generation > generation:
			generation = int(data.generation)
			active_slot = slot
			records = data.records.duplicate(true)
	if not writable:
		status = "Kayıt okunamıyor veya daha yeni sürüme ait · üzerine yazılmayacak."
	elif damaged:
		status = "Önceki sağlam kayıt kurtarıldı." if active_slot >= 0 else "Kayıt bozuk · yeni ilerleme ile başlanıyor."
	else:
		status = "Yerel ilerleme yüklendi." if active_slot >= 0 else "İlk seansın sonunda yerel kayıt oluşturulacak."

func record(source: String, result: Dictionary) -> bool:
	if not writable:
		return false
	if source not in SOURCES or result.size() != 4 or not result.get("completed") is bool:
		return false
	if not integer(result.get("score"), 0, 2740) or not integer(result.get("highest_floor"), 1, 3) or not integer(result.get("best_combo"), 0, 13):
		return false
	var candidate = records.duplicate(true)
	var row: Dictionary = candidate[source]
	row.sessions += 1
	row.completed += int(result.completed)
	row.best_score = maxi(row.best_score, result.score)
	row.highest_floor = maxi(row.highest_floor, result.highest_floor)
	row.best_combo = maxi(row.best_combo, result.best_combo)
	var payload = {"version": VERSION, "generation": generation + 1, "records": candidate}
	if not valid(payload):
		status = "Kayıt sınırına ulaşıldı · sonuç bu ekranda korunuyor."
		return false
	var slot = 1 if active_slot == 0 else 0
	var target = directory.path_join("progress-%d.json" % slot)
	if DirAccess.make_dir_recursive_absolute(directory) != OK or not write_atomic(target, JSON.stringify(payload)):
		status = "Kayıt yazılamadı · sonuç bu ekranda korunuyor. K: yeniden dene."
		return false
	records = candidate
	generation += 1
	active_slot = slot
	status = "Bu giriş kaynağının yerel ilerlemesi kaydedildi."
	return true

func write_atomic(target: String, content: String) -> bool:
	var temporary = target + ".tmp"
	var file = FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(content)
	file.flush()
	var error = file.get_error()
	file.close()
	if error == OK:
		error = DirAccess.rename_absolute(temporary, target)
	if error != OK:
		DirAccess.remove_absolute(temporary)
	return error == OK
