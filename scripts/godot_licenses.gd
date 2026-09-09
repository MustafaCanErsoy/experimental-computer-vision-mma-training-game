extends SceneTree

func _initialize() -> void:
	var args = OS.get_cmdline_user_args()
	if args.size() != 1:
		quit(1)
		return
	var file = FileAccess.open(args[0], FileAccess.WRITE)
	if file == null:
		quit(1)
		return
	file.store_string(JSON.stringify({"version": Engine.get_version_info(),
		"license": Engine.get_license_text(), "authors": Engine.get_author_info(),
		"copyright": Engine.get_copyright_info(), "third_party_licenses": Engine.get_license_info()}, "  "))
	file.close()
	quit(0)
