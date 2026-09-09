# Validation and measurement

ShadowMMA is an experiment. Its automated checks do not validate human punch recognition, professional technique, physical latency, or the teaching value of the game. Practical camera recognition remains unreliable.

## Existing automated checks

After completing source setup, run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\test_camera_ready_live.py
```

The Python suite covers movement rules, calibration, synthetic negative cases, reporting, event delivery, storage, and launcher lifecycle. Some launcher tests require the project-local Godot runtime and Windows process features.

The integration script uses generated image/landmark inputs with the real extraction, Tk, detector, local event bridge, and Godot processes. Physical camera creation is forbidden within that test. Generated successes establish software behavior under those inputs, not success on real footage.

`scripts/test_report_ui.py` checks the generated report in a locally installed Edge browser. `scripts/test_windows_bundle.py` validates a locally built package. These checks have additional platform/runtime requirements and generate local artifacts under ignored `build/` directories.

## Interpreting human evaluation

The laboratory (`Baslat.cmd`) has a manually started camera and a labelled trial workflow. Participant confirmation records whether the requested movement was performed; it is not an expert assessment of technique. Keep performed-movement labels independent of what the detector reports.

Measure each of the three movement classes separately, include non-punch movements, and report missed movements, wrong classes, duplicate events, false positives, and unusable tracking coverage. Report unevaluable and interrupted trials separately. Automatic recognition journals have no independent ground truth, so their detected-event totals cannot establish accuracy.

## Optional physical latency method

The laboratory's external-latency input refers to this method. It is optional; leave the field empty if no measurement was made.

1. Use an external high-frame-rate recording that shows the movement and screen together.
2. Identify the frame where the punch extension becomes visibly clear and the first frame showing the on-screen detection notification.
3. Calculate `(notification frame - movement frame) / recording FPS * 1000` milliseconds.
4. Use the median of at least five repetitions for the laboratory's external-latency field. Retain the event definition and recording FPS with your measurement.

This records movement-to-notification delay under that event definition. It differs from model inference time and software read-to-render timings. Frame resolution is about 16.7 ms at 60 FPS and 8.3 ms at 120 FPS. No physical-latency result is claimed by the public source release.
