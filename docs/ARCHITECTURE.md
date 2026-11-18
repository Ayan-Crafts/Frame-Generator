# Architecture — TrackNetV1 Dataset Prepper 2.1

This document describes the code as it exists in this repository. The
project's working name in the code and UI is **Frame Generator**; the
distributed product name is **TrackNetV1 Dataset Prepper**.

## 1. What the application does

Prepares training data for [TrackNet V1](https://nol.cs.nctu.edu.tw:234/open-source/TrackNet)
ball tracking in three stages:

1. **Video → frames** — extracts every frame of every video in a folder tree
   to numbered JPEGs, using NVIDIA NVDEC hardware decoding when it is verified
   to work and the CPU otherwise. Resumable, cancellable, crash-tolerant.
2. **Annotation** — a desktop tool for clicking the ball centre in each frame
   and labelling visibility (visible / partially occluded / fully occluded /
   out of bounds / severe motion blur). Writes `annotations.csv` per folder.
3. **Conversion** — turns an annotated folder into TrackNet V1 training data
   (640×360 images, Gaussian heatmaps, `training_model1.csv` /
   `testing_model1.csv`).

An experimental fourth tool (`tools/tracknet_assistant/`) evaluates a
pre-trained TrackNet V1 model against manual annotations.

## 2. Start-up

```
TrackNetPrepper(.exe) / python -m app.main / python app/main.py
  └─ app/main.py: parse args → configure_logging() → QApplication → MainWindow
       ├─ HardwareDetector().detect()          presence only (nvidia-smi / WMI)
       ├─ FunctionTask(get_report)             background: FFmpeg probe + GPU self-test
       ├─ TelemetryThread                      background: nvidia-smi every 1.5 s
       └─ QTabWidget
            ├─ "VIDEO → FRAMES"   (converter page, in MainWindow)
            └─ "ANNOTATION TOOL"  (AnnotationTab)

tracknet-prepper-cli(.exe) / python -m app.cli
  └─ app/cli.py: doctor | extract | convert-tracknet
```

Nothing blocks the GUI thread: the capability check, frame counting,
output-size scans, GPU telemetry and the export itself all run on `QThread`s.

## 3. Components

| Component | File | Purpose | Depends on | Status (2.1) |
|---|---|---|---|---|
| Entry point | `app/main.py` | GUI start, `--smoke-test`, `--screenshot` | PySide6 | Fully functional |
| CLI | `app/cli.py` | `doctor`, `extract`, `convert-tracknet` | exporter, capabilities | Fully functional (new) |
| Main window | `app/ui/main_window.py` | Converter UI, controls, telemetry cards, system check | PySide6, worker, capabilities | Fully functional |
| Background helpers | `app/ui/background.py` | `FunctionTask`, `TelemetryThread`, fast dir sizing | PySide6, `SystemMonitor` | Fully functional (new) |
| Annotation tool | `app/ui/annotation_tab.py` | Frame viewer, 5 states, CSV/RANGES/STATISTICS/SETTINGS pages | PySide6 | Functional; SETTINGS (SAM 2.1) is UI-only, see §9 |
| Export worker | `app/processing/worker.py` | Batch loop on a `QThread`; pause/stop/cancel; per-video failure isolation | exporter, jobs | Fully functional |
| Exporter | `app/processing/exporter.py` | Probe, pipeline selection, FFmpeg run, resume, validation | FFmpeg, resume, resource manager | Fully functional |
| Resume | `app/processing/resume.py` | Find last valid contiguous frame; `.complete` marker | Pillow | Fully functional |
| Resource manager | `app/processing/resource_manager.py` | FFmpeg thread count from CPU/RAM/disk/GPU load | psutil, nvidia-smi | Fully functional |
| Scanner | `app/processing/scanner.py` | Recursive video discovery; collision-free output names | — | Fully functional |
| Jobs | `app/jobs/job_manager.py` | JSON job state in `~/.frame-generator/jobs` | — | Functional (no "resume after restart" UI yet) |
| Capabilities | `app/hardware/capabilities.py` | FFmpeg + NVIDIA detection and **functional verification** | FFmpeg, nvidia-smi | Fully functional (new) |
| GPU presence | `app/hardware/detector.py` | Display-only GPU name/vendor | nvidia-smi, WMI | Functional |
| System monitor | `app/monitoring/system.py` | GPU telemetry sample (util, NVDEC util, VRAM, temp) | nvidia-smi | Functional (now used) |
| FFmpeg locator | `app/utils/ffmpeg.py` | Find FFmpeg (override → bundled → PATH), probe features | FFmpeg | Fully functional |
| Paths / logging / subprocess | `app/utils/{paths,logging_setup,proc}.py` | Per-user dirs, rotating log, no-console UTF-8 subprocesses | — | New |
| TrackNet converter | `app/tools/convert_to_tracknet.py` (+ shim `tools/convert_to_tracknet.py`) | Annotations → TrackNet V1 training set | Pillow | Fully functional |
| TrackNet assistant | `tools/tracknet_assistant/tracknet_assistant.py` | Evaluate a TrackNet V1 model vs. annotations | TensorFlow, OpenCV, numpy, external TrackNet V1 repo + weights | Experimental, not packaged |
| Benchmark | `tools/benchmark_extraction.py` | CPU vs GPU timing with NVDEC/CPU sampling | exporter | Developer tool |
| Placeholders | `app/ui/converter_tab.py`, `app/database/` | Empty modules kept from v2.0 | — | Unused |

Independent components: the annotation tool and the converter never need
FFmpeg or a GPU; extraction never needs the annotation tool. If FFmpeg is
missing, extraction is disabled with an explanation and everything else works.

## 4. Dependencies

| Dependency | Required? | How it is provided |
|---|---|---|
| Python 3.12, PySide6-Essentials 6.12, psutil, Pillow | Required | Frozen into the app by PyInstaller (never installed into a system Python) |
| FFmpeg + FFprobe ≥ 5.1 | Required for extraction only | Windows: optional bundled copy (installer component); Linux: Ubuntu `ffmpeg` package (apt `Recommends`); or any FFmpeg on `PATH`; or `TNP_FFMPEG`/`TNP_FFPROBE` |
| NVIDIA driver | Optional (GPU decode) | User-installed; never bundled or modified |
| CUDA toolkit | **Not needed** | FFmpeg's NVDEC path loads `nvcuvid`/`cuda` from the driver at run time |
| Qt X11 libraries (Linux) | Required for the GUI | `.deb` `Depends` → apt installs what is missing |
| TensorFlow, OpenCV, numpy | Only for `tracknet_assistant` | Developer environment; not packaged |

## 5. Data flow

```
input folder (videos, any depth)
  │ DatasetScanner.scan()           → sorted list of videos (.mp4 .mkv .avi .mov .webm ...)
  │ output_names()                  → <stem>, or <parent>__<stem> when names collide
  ▼
ExportWorker (QThread) ── per video ──► VideoExporter.export_video()
  │                                       1. ffprobe: fps, frame count (nb_frames, else duration×fps), VFR flag
  │                                       2. ResumeManager.inspect(): last valid contiguous frame N
  │                                       3. resume_plan(N): seek point + frames to discard
  │                                       4. ffmpeg … -start_number N+1 -progress pipe:1 <out>/%06d.jpg
  │                                       5. validate count; write .complete
  ▼
<output>/<name>/000001.jpg … 00000N.jpg  + .complete
  │
  ▼ ANNOTATION TOOL (one frame folder at a time)
<output>/<name>/annotations.csv   frame,x,y,visibility,x1,y1,x2,y2,source,confidence,status
<output>/<name>/annotated/*.jpg   optional visual check copies
  │
  ▼ tracknet-prepper-cli convert-tracknet --input <output>/<name> --output <dataset>
<dataset>/images/ heatmaps/ training_model1.csv testing_model1.csv conversion_report.json
```

Output naming and formats are unchanged from v2.0 (`%06d.jpg` from 1, JPEG
`-q:v 2`, same CSV columns) so existing datasets and partial exports remain
compatible. The only naming change applies when two videos in one job share a
file name — v2.0 silently wrote both into the same folder.

## 6. Video pipeline and GPU acceleration

### Pipelines

| Stage | GPU pipeline | CPU pipeline |
|---|---|---|
| Demux | CPU | CPU |
| Decode | **GPU (NVDEC)** `-hwaccel cuda -hwaccel_output_format cuda` | CPU (libavcodec) |
| GPU → system memory | `hwdownload,format=nv12` (PCIe copy) | — |
| Seek discard | `select=gte(n,D)` on CPU | same |
| Colour conversion + JPEG encode | CPU (swscale + MJPEG encoder) | CPU |
| Write | CPU | CPU |

Only decoding is accelerated. NVENC encodes video streams and has no role in
writing JPEGs, so it is detected and reported but never used. The UI shows
the exact pipeline per video (`GPU decode (NVDEC) → CPU JPEG encode`), and
says "VERIFIED" only after a real test decode succeeds.

### Capability levels (`app/hardware/capabilities.py`)

1. **GPU detected** — `nvidia-smi` lists a GPU (name, VRAM, compute capability, driver, CUDA driver API).
2. **FFmpeg support** — the FFmpeg build lists the `cuda` hwaccel and the `hwdownload` filter.
3. **NVDEC verified** — the production command is run on `app/resources/selftest_h264.mp4` and must exit 0.
4. **NVENC verified** — an H.264 NVENC encode of a test pattern (informational).

### Mode selection and fallback

* **AUTO** (default): GPU pipeline if level 3 passed, else CPU. If NVDEC
  rejects a particular stream (H.264 4:4:4, Hi10P, 10-bit HEVC with the NV12
  download, codecs an older GPU lacks), the video continues on the CPU from
  the last good frame and a warning names the FFmpeg error.
* **GPU**: always NVDEC; an unsupported stream is reported as a failure.
* **CPU**: never touches the GPU.

### Resume

Frames are written sequentially, so only the tail of an interrupted run can
be damaged. On resume, the contiguous run `000001..N` is found, the last 8
frames are fully decoded and checked for the JPEG end-of-image marker, and
anything after the first bad frame is deleted. Extraction restarts at frame
N+1 using `resume_plan()`: seek to a keyframe 5 s earlier (to half a frame
before a frame boundary, which makes FFmpeg's accurate-seek cut unambiguous)
and discard frames up to N. Variable-frame-rate sources are decoded from the
start instead of seeking. Tests check that a resumed extraction is
byte-identical to an uninterrupted one at several resume points, for H.264
(B-frames) MP4, MKV, MPEG-4 AVI and VP9 WebM, on CPU and GPU.

### Completion rules

* MP4/MOV with a container frame count: decode exactly that many; accept up
  to max(2 frames, 0.5 %) fewer if FFmpeg reached end of file (warning).
* MKV/WebM (count estimated from duration): decode to end of file; accept a
  max(3 frames, 2 %) difference (warning).
* Larger shortfall (truncated/corrupted file): frames kept, video **not**
  marked complete, error reported, batch continues.

### Robustness

* FFmpeg stdout (progress) and stderr are drained on separate threads
  (v2.0 could deadlock on a chatty stderr); the control loop polls every
  250 ms so Pause/Stop/Cancel respond even if FFmpeg stalls.
* Stop sends `q` to FFmpeg (clean last frame), then terminate, then kill.
* Disk space: refuses to start below 0.5 GB free, warns when the estimate
  exceeds free space, and stops (keeping frames) below 0.25 GB.
* Every subprocess uses UTF-8 decoding and, on Windows, `CREATE_NO_WINDOW`.

## 7. Threading model

| Thread | Work | Communicates via |
|---|---|---|
| GUI | widgets, timers (1 s stats) | — |
| `ExportWorker` (QThread) | batch loop, FFmpeg control | Qt signals (queued) |
| FFmpeg pumps (Python threads) | read stdout / stderr | `queue.Queue`, deque |
| `FunctionTask` (QThread) | capability report, frame count, output size | `succeeded` signal |
| `TelemetryThread` (QThread) | nvidia-smi sampling | `sample` signal |

`ExportWorker` is parented to the window and released with `deleteLater()`
only after `QThread.finished`; v2.0 dropped the last reference from a slot
while `run()` was still executing, which can abort the process with
"QThread: Destroyed while thread is still running".

## 8. Files written

| What | Where | Removed by uninstall? |
|---|---|---|
| Frames, `.complete` | user-chosen output folder | Never |
| `annotations.csv` (atomic replace), `annotated/` | the frame folder | Never |
| Logs (rotating 5 × 2 MB), `install-check.json` | Windows `%LOCALAPPDATA%\TrackNetPrepper`; Linux `~/.local/state/tracknet-prepper` | Only if the user ticks it (Windows); never (Linux) |
| Job history | `~/.frame-generator/jobs` (unchanged from v1) | Same as logs |
| Application | Windows `%LOCALAPPDATA%\Programs\…` (per-user) or `Program Files`; Linux `/opt/tracknet-prepper` | Yes |

Overrides for tests/portable use: `TNP_DATA_DIR`, `TNP_JOBS_DIR`,
`TNP_FFMPEG`, `TNP_FFPROBE`.

## 9. Known gaps (not regressions)

* SETTINGS page lists SAM 2.1 models and a confidence threshold, but no SAM
  inference is wired up; `set_model_annotation()` is the integration hook.
* Jobs interrupted by closing the app can be resumed by starting the same
  input/output again (completed videos are skipped, partial ones resume); there
  is no "resume previous job" list in the UI.
* GPU decoding uses one GPU (device 0).

## 10. Packaging architecture

```
                     app/ (source)
                         │ PyInstaller (one spec, packaging/pyinstaller/tracknet_prepper.spec)
                         ▼
          dist/TrackNetPrepper/   GUI exe + CLI exe + _internal/ (Python, Qt, Pillow, psutil, resources)
             │                                   │
   Windows   │ + ffmpeg/ (bundled)               │ Linux (built in ubuntu:24.04)
             ▼                                   ▼
  Portable zip   Inno Setup installer      .deb: /opt/tracknet-prepper, /usr/bin wrappers,
                 (ffmpeg = optional        .desktop + icon; Depends: Qt X11 libs;
                  component, auto-         Recommends: ffmpeg (apt reuses or installs)
                  selected only if no
                  compatible FFmpeg)
```

Build scripts: `packaging/windows/build_windows.ps1`,
`packaging/linux/docker_build.{sh,ps1}` → `packaging/linux/build_linux.sh`.
Installation tests: `packaging/linux/test_deb.sh` (fresh container), and the
manual Windows checklist in `docs/INSTALLATION_WINDOWS.md`.
