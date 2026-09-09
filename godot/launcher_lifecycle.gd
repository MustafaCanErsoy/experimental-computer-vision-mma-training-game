extends Node
## Supervisor's private temporary token allows normal SceneTree shutdown.
var stop_file: String = ""
var elapsed: float = 0.0

func _ready() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--stop-file="):
			stop_file = argument.trim_prefix("--stop-file=")
	set_process(not stop_file.is_empty())

func _process(delta: float) -> void:
	elapsed += delta
	if elapsed >= 0.1:
		elapsed = 0.0
		if FileAccess.file_exists(stop_file):
			get_tree().quit()
