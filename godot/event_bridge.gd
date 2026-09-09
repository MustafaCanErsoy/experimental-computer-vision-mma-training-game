extends RefCounted
## Loopback-only, lossy numeric input. Encounter remains the only game authority.
signal strike_received(move: String, outcome: String)
signal prompt_expired

const VERSION = 1
const LEASE_SECONDS = 0.5
const TIMEOUT = 1.0
var socket = PacketPeerUDP.new()
var source: String
var session: String = Crypto.new().generate_random_bytes(16).hex_encode()
var link: String = ""
var client: String = ""
var peer_port: int = 0
var connected: bool = false
var source_ready: bool = false
var status: String = "Yerel üretici bekleniyor"
var last_seen: float = 0.0
var last_publish: float = -1.0
var signature: String = ""
var revision: int = 0
var lease_id: int = 0
var leases: Dictionary = {}
var last_event: int = 0
var accepted_id: int = 0
var manual_paused: bool = false
var guard_held: bool = false
var last_guard: float = -1.0
var guard_event: int = 0
var diagnostic_status: String = "Kamera hazırlanıyor…"
var diagnostic_result: String = ""
var recording: bool = false
var last_diagnostic: float = -1.0
var control_id: int = 0

func control(action: String) -> void:
	if not connected or peer_port == 0:
		return
	control_id += 1
	var packet = {"v": VERSION, "type": "control", "source": source, "client": client,
		"session": session, "link": link, "id": control_id, "action": action}
	socket.set_dest_address("127.0.0.1", peer_port)
	socket.put_packet(JSON.stringify(packet).to_utf8_buffer())

func receipt(event: int, outcome: String) -> void:
	var packet = {"v": VERSION, "type": "receipt", "source": source, "client": client,
		"session": session, "link": link, "event": event, "outcome": outcome}
	socket.set_dest_address("127.0.0.1", peer_port)
	socket.put_packet(JSON.stringify(packet).to_utf8_buffer())

func has_guard(now: float) -> bool:
	return source == "camera" and connected and source_ready and guard_held and now - last_guard <= 0.25

func toggle_camera_pause(e, now: float) -> void:
	manual_paused = not manual_paused
	e.set_paused(true, now)
	status = "Elle duraklatıldı · P: eller görünürken devamı etkinleştir" if manual_paused else "Ellerini kısa bir an sabit tut · otomatik devam"
	sync(e)

func start(kind: String, port: int) -> Error:
	source = kind
	var error = socket.bind(port, "127.0.0.1")
	if error != OK:
		status = "Yerel bağlantı açılamadı · port kullanımda olabilir"
	return error

func close() -> void:
	socket.close()

func restart(e, now: float) -> void:
	# Keep the bound socket, but invalidate every identity from the previous run.
	session = Crypto.new().generate_random_bytes(16).hex_encode()
	accepted_id = 0
	manual_paused = false
	drop(e, now)

func sync(e) -> void:
	var current = "%d/%s/%d/%s" % [e.floor_number, e.phase, e.step, e.paused]
	if current != signature:
		signature = current
		revision += 1
		leases.clear()
		last_publish = -1.0

func drop(e, now: float) -> void:
	e.set_paused(true, now)
	connected = false
	source_ready = false
	guard_held = false
	guard_event = 0
	last_guard = -1.0
	diagnostic_status = "Bağlantı bekleniyor"
	diagnostic_result = ""
	last_diagnostic = -1.0
	peer_port = 0
	client = ""
	link = ""
	leases.clear()
	status = "Bağlantı kesildi · yeniden bağlantı bekleniyor"
	sync(e)

func publish(e, now: float) -> void:
	if peer_port == 0:
		return
	lease_id += 1
	leases[lease_id] = now
	for key in leases.keys():
		if now - leases[key] > LEASE_SECONDS:
			leases.erase(key)
	var packet = {"v": VERSION, "type": "state", "client": client, "source": source,
		"session": session, "link": link, "lease": lease_id,
		"encounter": session + ":" + str(e.floor_number), "prompt": str(revision),
		"phase": e.phase, "paused": e.paused, "move": e.requested()}
	socket.set_dest_address("127.0.0.1", peer_port)
	socket.put_packet(JSON.stringify(packet).to_utf8_buffer())
	last_publish = now

func fields(packet: Dictionary, names: Array) -> bool:
	if packet.size() != names.size():
		return false
	for key in names:
		if not packet.has(key):
			return false
	return true

func integer(value, low: int, high: int) -> bool:
	return (value is float or value is int) and is_finite(float(value)) and value == floor(value) and value >= low and value <= high

func receive(p: Dictionary, port: int, e, now: float) -> void:
	if not integer(p.get("v"), 1, 1) or p.get("source") != source:
		return
	if p.get("type") == "hello":
		if not fields(p, ["v", "type", "source", "client"]) or not p.client is String or p.client.length() != 32:
			return
		if peer_port == 0:
			peer_port = port
			client = p.client
			link = Crypto.new().generate_random_bytes(16).hex_encode()
			last_event = 0
			last_seen = now
			e.set_paused(true, now)
			sync(e)
		if peer_port == port and client == p.client:
			publish(e, now)
		return
	if port != peer_port or p.get("client") != client or p.get("link") != link or link.is_empty():
		return
	if p.get("type") == "diagnostic":
		if source != "camera" or not fields(p, ["v", "type", "source", "client", "link", "lease", "status", "result", "recording"]):
			return
		if not p.status is String or not p.result is String or not p.recording is bool or p.status.length() > 180 or p.result.length() > 180 or not valid_lease(p.lease, now):
			return
		diagnostic_status = p.status
		diagnostic_result = p.result
		recording = p.recording
		last_diagnostic = now
	elif p.get("type") == "pulse":
		if not fields(p, ["v", "type", "source", "client", "link", "lease", "ready"]) or not p.ready is bool:
			return
		if not valid_lease(p.lease, now):
			return
		last_seen = now
		connected = true
		source_ready = p.ready
		if not source_ready:
			guard_held = false
			e.set_paused(true, now)
		status = "Üretici hazır · P ile devam et" if source_ready else "Algılama hazır değil · kamera / kalibrasyon / takip bekleniyor"
		if source == "camera":
			if manual_paused:
				status = "Elle duraklatıldı · P: eller görünürken devamı etkinleştir"
			elif source_ready:
				status = "Ellerini kısa bir an sabit tut · otomatik başlayacak"
		sync(e)
	elif p.get("type") == "guard":
		if source != "camera" or not fields(p, ["v", "type", "source", "client", "link", "lease", "event", "held"]):
			return
		if not p.held is bool or not integer(p.event, 1, 2147483647) or p.event <= guard_event or not valid_lease(p.lease, now):
			return
		guard_event = int(p.event)
		guard_held = p.held and connected and source_ready
		last_guard = now
		# Guard is classified by Python; encounter changes remain authoritative here.
		if has_guard(now) and not manual_paused and e.paused and e.phase != "results":
			e.set_paused(false, now)
			sync(e)  # Revoke all pre-resume hit/guard leases.
	elif p.get("type") == "hit":
		if not fields(p, ["v", "type", "source", "client", "link", "lease", "event", "encounter", "prompt", "move", "age_ms"]):
			return
		if not integer(p.event, 1, 2147483647):
			return
		if p.event <= last_event:
			receipt(int(p.event), "duplicate")
			return
		# Even rejected events cannot later be relabelled and replayed.
		last_event = int(p.event)
		if not connected or not source_ready or e.paused or e.phase != "fight":
			receipt(int(p.event), "inactive")
			return
		if p.encounter != session + ":" + str(e.floor_number) or p.prompt != str(revision):
			receipt(int(p.event), "stale_prompt")
			return
		if not valid_lease(p.lease, now) or not integer(p.age_ms, 0, 250) or p.move not in e.MOVES:
			receipt(int(p.event), "stale_lease")
			return
		accepted_id += 1
		var outcome: String = e.strike(p.move, accepted_id, now)
		receipt(int(p.event), outcome)
		strike_received.emit(p.move, outcome)
		sync(e)

func valid_lease(value, now: float) -> bool:
	return integer(value, 1, 2147483647) and leases.has(int(value)) and now - leases[int(value)] <= LEASE_SECONDS

func poll(e, now: float) -> void:
	if not socket.is_bound():
		e.set_paused(true, now)
		return
	if peer_port != 0 and now - last_seen > TIMEOUT:
		drop(e, now)
	if not connected or not source_ready:
		e.set_paused(true, now)
	if e.advance(now):
		prompt_expired.emit()
	sync(e)
	# Bounded work and payloads; never deserialize engine objects or image data.
	for i in range(mini(socket.get_available_packet_count(), 64)):
		var bytes = socket.get_packet()
		var port = socket.get_packet_port()
		if socket.get_packet_ip() != "127.0.0.1" or bytes.size() > 1024:
			continue
		var parser = JSON.new()
		if parser.parse(bytes.get_string_from_utf8()) == OK and parser.data is Dictionary:
			receive(parser.data, port, e, now)
	if now - last_publish >= 0.1:
		publish(e, now)
