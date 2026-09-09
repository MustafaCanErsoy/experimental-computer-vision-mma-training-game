"""Model/camera smoke check. Never saves images or landmarks."""
import argparse
import json
import sys
from pathlib import Path
from time import perf_counter, sleep
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from shadowmma.vision import Pose, Camera, MODEL, MODEL_SHA256
from shadowmma.metrics import percentiles
import hashlib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--seconds", type=float, default=5.)
    parser.add_argument("--mjpg", action="store_true", help="Try MJPG capture transport")
    args = parser.parse_args()
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
        raise RuntimeError("Model hash mismatch")
    pose = Pose()
    camera = None
    try:
        start = perf_counter()
        landmarks, _ = pose.process(np.zeros((480, 640, 3), dtype=np.uint8), start)
        result = {"model_load_and_blank_inference": "PASS", "blank_pose_count": int(bool(landmarks)),
                  "model_sha256": MODEL_SHA256, "human_movement_test": "NOT_PERFORMED",
                  "frames_saved": 0, "camera_requested": args.camera is not None}
        if args.camera is not None:
            camera = Camera(args.camera, mjpg=args.mjpg)
            capture_start = perf_counter()
            deadline = capture_start+max(1., args.seconds)
            sequence, samples, inference, frames, shape = -1, [], [], 0, None
            received_times = []
            while perf_counter() < deadline:
                if camera.error:
                    raise RuntimeError(camera.error)
                latest = camera.read()
                if latest is None or latest[0] == sequence:
                    sleep(.01)
                    continue
                sequence, received, frame = latest
                received_times.append(received)
                begin = perf_counter()
                pose.process(frame, received)
                inference.append((perf_counter()-begin)*1000)
                samples.append((perf_counter()-received)*1000)
                frames += 1
                shape = list(frame.shape)
            if not frames:
                raise RuntimeError("No camera frames within timeout")
            result.update(camera_backend=camera.backend, processed_frames=frames, shape=shape,
                          mjpg_requested=args.mjpg,
                          inference=percentiles(inference), frame_received_to_inference_end=percentiles(samples),
                          first_frame_wait_ms=round((received_times[0]-capture_start)*1000, 2),
                          processed_fps=round((frames-1)/(received_times[-1]-received_times[0]), 2) if frames > 1 else None,
                          sample_interval=percentiles([(b-a)*1000 for a, b in zip(received_times, received_times[1:])]),
                          software_pipeline_only=True)
        print(json.dumps(result, indent=2))
    finally:
        if camera:
            camera.close()
        pose.close()


if __name__ == "__main__":
    main()
