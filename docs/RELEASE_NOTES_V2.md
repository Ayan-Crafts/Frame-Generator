# TrackNetV1 Dataset Prepper 2.1.0 — "Alela Polema" stabilization release

**Release date:** 2026-11-18
**Supersedes:** v2.0.0 (2026-08-20)
**Licence:** MIT (application). Bundled FFmpeg: see `ffmpeg/LICENSE*` in the install folder.

2.1.0 is the V2 stabilization release: no new workflows, the same output
formats, and fixes for every defect found in an audit of v2.0. It is also the
first release with real installers for Windows and Ubuntu.

## Downloads

| File | Platform | Notes |
|---|---|---|
| `TrackNetV1_Dataset_Prepper_V2_Setup.exe` | Windows 10 1809+ / 11, x64 | Installer; per-user (no admin) or all users |
| `TrackNetV1_Dataset_Prepper_V2_Portable.zip` | Windows 10 1809+ / 11, x64 | Unzip and run, nothing installed |
| `tracknet-prepper_2.1.0_amd64.deb` | Ubuntu 24.04 LTS, x86-64 | `sudo apt install ./tracknet-prepper_2.1.0_amd64.deb` |
| `SHA256SUMS-*.txt` | — | Checksums |

No Python, pip, CUDA toolkit or manual PATH setup is needed on either platform.

## Compatibility

| Item | Requirement / version |
|---|---|
| Python runtime (bundled) | 3.12 (Windows 3.12.10, Linux 3.12.3) |
| Qt (bundled) | PySide6-Essentials 6.12.0 |
| Other bundled libraries | Pillow 13.0.0, psutil 7.2.2 |
| FFmpeg | ≥ 5.1. Windows: optional bundled copy; Linux: Ubuntu `ffmpeg` 6.1.1 via apt |
| NVIDIA GPU decoding | Any NVDEC-capable NVIDIA GPU (Kepler or newer) with a working driver. Not bundled, never modified. CUDA Toolkit not required |
| Tested NVIDIA GPU | GeForce RTX 4050 Laptop GPU (Ada, 6 GB), driver 621.24 (Windows) / 620.73.02 via WSL2 (Ubuntu container) |
| CPU fallback | Always available; same output, slower |

## What changed

### Video → frames (extraction)

* **CPU pipeline and automatic fallback.** v2.0 only had the CUDA command
  line; on machines without a working NVIDIA setup every export failed. Now:
  AUTO (GPU when verified, CPU otherwise, per-video CPU fallback when NVDEC
  rejects a stream), GPU-only and CPU-only modes.
* **Honest acceleration status.** The header used to say "NVIDIA
  ACCELERATION" whenever `nvidia-smi` existed (and "AMD ACCELERATION" for AMD
  cards, which have no pipeline). It now reflects a real NVDEC test decode,
  and each video shows the pipeline actually used
  (`GPU decode (NVDEC) → CPU JPEG encode` or `CPU decode → CPU JPEG encode`).
* **Fixed: MKV/WebM exported as "complete" with zero frames.** These
  containers usually have no frame count, which v2.0 turned into 0.
* **Fixed: resume produced the wrong frame at the seam.** After Pause/Stop
  and Resume, the first resumed frame was the *next* source frame (one frame
  skipped, one duplicated) because the seek landed exactly on a frame
  boundary. Resumed extractions are now byte-identical to uninterrupted ones
  (tested for H.264 MP4 with B-frames, MKV, MPEG-4 AVI, VP9 WebM; CPU and GPU).
* **Fixed: truncated last frame kept after a crash.** PIL's `verify()` does
  not detect truncated JPEGs; resume now checks the JPEG end marker and
  decodes the tail frames.
* **Fixed: one bad file stopped the whole batch** (and left the UI in a
  running state). Failed videos are listed in a summary; the batch continues.
* **Fixed: possible deadlock** when FFmpeg wrote a lot to stderr (damaged
  files), and Pause/Stop could wait indefinitely on a stalled FFmpeg.
* **Fixed: same-named videos in different folders overwrote each other**
  (`match1/cam.mp4`, `match2/cam.mp4` → one `cam/` folder; the second was
  skipped as "complete"). Colliding names now get their folder prefixed;
  non-colliding names are unchanged, so existing exports still resume.
* **Fixed: frame counter restarted at 0 after resume;** ETA was computed
  from the wrong totals; TOTAL FRAMES showed "Calculating..." forever.
* **Disk space**: refuses to start with < 0.5 GB free, warns when the
  estimate exceeds free space, stops safely (keeping frames) when the disk
  fills. v2.0 measured free space on the wrong drive.
* Clear messages for empty, corrupted, audio-only and non-video files.
* FFmpeg is found on `PATH` (v2.0 required `packaging/ffmpeg/ffmpeg.exe`),
  version-checked (≥ 5.1) and feature-probed.

### Stability and UI

* **Fixed: possible crash "QThread: Destroyed while thread is still
  running"** — the window released the export thread from inside its own
  signals.
* **Fixed: GUI freezes** — `nvidia-smi` and a recursive scan of the entire
  output folder ran on the GUI thread every second and on every progress
  update. All such work now runs in background threads.
* **Fixed: console windows flashing** on Windows for every `nvidia-smi` /
  `ffmpeg` call in the packaged app.
* **Fixed: CANCEL & DELETE after PAUSE did nothing** and left the UI stuck.
* **Fixed: layout squashed on laptop screens** (empty SELECT buttons,
  overlapping cards at 1366×768 or 125 % scaling) — the page now scrolls and
  the controls stay pinned at the bottom.
* **Fixed: crash at start-up in containers/VMs** without disk counters.
* Closing the window during an export asks first and stops FFmpeg cleanly.
* New **SYSTEM CHECK** (full dependency/GPU report, copyable) and **LOGS** buttons.
* Rotating log file; uncaught exceptions are logged.

### Annotation tool

* **Restored keyboard shortcuts** (←/→, Shift+←/→, Space, Enter) — documented
  in v2.0 but lost in a UI refactor.
* **Fixed: PLAY button raised an error** and did nothing.
* **annotations.csv is written atomically** — a crash or full disk can no
  longer truncate it.
* Asks to save unsaved annotations when switching folders or closing.
* CSV/RANGES tables rebuild only when shown (clicks no longer slow down on
  long sequences).

### Tools

* **TrackNet converter** (`convert-tracknet`): `--validation-ratio` was
  ignored (always 80/20) — fixed; new `--heatmap-format png` for lossless
  heatmaps (default stays `jpg` for compatibility); clear usage errors.
  Bundled in the installers as `tracknet-prepper-cli convert-tracknet`;
  `python tools/convert_to_tracknet.py` still works.
* **TrackNet assistant**: removed the hard-coded `S:\…\TrackNet-V1` path
  (`--tracknet-dir` / `TRACKNET_V1_DIR`). Still a developer tool (needs
  TensorFlow) and not part of the installers.
* New `tracknet-prepper-cli`: `doctor`, `extract` (headless), `convert-tracknet`.
* New `tools/benchmark_extraction.py`.

### Development

* `python app/main.py` works (it failed with `ModuleNotFoundError` in v2.0).
* Test suite: 89 tests (extraction correctness vs. FFprobe, corrupted input,
  GPU/CPU/fallback, resume seams, cancel, disk full, GUI flows, annotation,
  converter, CLI, dependency detection).
* `requirements.txt` / `requirements-dev.txt` with pinned versions; PySide6
  *Essentials* only (the full meta-package adds ~500 MB of unused Qt modules).
* Compiled `__pycache__/*.pyc` files removed from the repository.

## Compatibility notes

* Output layout and names are unchanged (`<output>/<video>/%06d.jpg`,
  `.complete`, `annotations.csv` columns), except for the name-collision fix
  above.
* Job history stays in `~/.frame-generator/jobs`.
* Converter default output is unchanged.

## Known issues and limitations

* The SETTINGS page's SAM 2.1 options are not connected to a model (UI only),
  as in v2.0.
* No "resume previous job" list after restarting the app; start the same
  input/output again — finished videos are skipped and partial ones resume.
* Only GPU *decoding* is accelerated; JPEG encoding is CPU-bound, so on fast
  GPUs the CPU limits throughput (see `docs/TEST_RESULTS.md`).
* Variable-frame-rate videos resume by decoding from the start (exact but slower).
* Windows binaries are not code-signed (SmartScreen warning).
* The Linux package targets Ubuntu 24.04+ (glibc 2.39); it was tested in
  Docker containers, not on a physical Ubuntu desktop.
* Docker users need `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video` for NVDEC.

See `docs/TEST_RESULTS.md` for exactly what was tested and how.
