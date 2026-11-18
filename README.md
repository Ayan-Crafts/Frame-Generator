# 🎬 TrackNetV1 Dataset Prepper (Frame Generator)

<div align="center">

[![Release: v2.1.0](https://img.shields.io/badge/Release-v2.1.0--Alela--Polema-blue.svg)](docs/RELEASE_NOTES_V2.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PySide6-Essentials/)
[![GPU](https://img.shields.io/badge/GPU%20decode-NVIDIA%20NVDEC-76B900.svg?logo=nvidia&logoColor=white)](docs/ARCHITECTURE.md#6-video-pipeline-and-gpu-acceleration)
[![Platforms](https://img.shields.io/badge/Platforms-Windows%2010%2F11%20%7C%20Ubuntu%2024.04-0078D6.svg)](#-installation)

**Video-to-frames extraction, ball annotation and TrackNet V1 dataset conversion in one desktop app.**

[Features](#-features) • [Installation](#-installation) • [GPU & CPU](#-gpu-acceleration-and-cpu-fallback) • [Workflows](#-workflows) • [Benchmarks](#-benchmarks) • [Troubleshooting](#-troubleshooting) • [Development](#-development)

</div>

---

## 📌 Overview

Preparing [TrackNet V1](https://nol.cs.nctu.edu.tw:234/open-source/TrackNet) ball-tracking data
means turning hours of sports video into numbered frames, marking the ball in each
frame, and converting the result into TrackNet's heatmap format. This application does
all three:

1. **VIDEO → FRAMES** — extracts every frame of every video in a folder tree to JPEGs,
   decoding on an NVIDIA GPU (NVDEC) when that is *verified* to work, otherwise on the
   CPU. Pause, resume, stop and cancel at any time; resumed output is frame-exact.
2. **ANNOTATION TOOL** — click the ball, label visibility (visible, partially occluded,
   fully occluded, out of bounds, severe motion blur), navigate with the keyboard,
   and keep `annotations.csv` in TrackNet's column layout.
3. **TrackNet conversion** — `tracknet-prepper-cli convert-tracknet` builds 640×360
   images, Gaussian heatmaps and `training_model1.csv` / `testing_model1.csv`.

## ✨ Features

### Video → frames
- NVIDIA **NVDEC** hardware decoding with an actual self-test at start-up; the header
  says *VERIFIED* only if a real test clip decoded on the GPU.
- **AUTO / GPU / CPU** modes. AUTO falls back to the CPU per video when the GPU cannot
  decode a stream (e.g. H.264 4:4:4, some 10-bit formats, codecs older GPUs lack).
- Shows the real pipeline for each video, e.g. `GPU decode (NVDEC) → CPU JPEG encode`.
- MP4, MOV, MKV, WebM, AVI, MPEG, TS/MTS/M2TS, WMV, FLV, M4V — any codec FFmpeg decodes.
- Output: `<output>/<video name>/000001.jpg …` (JPEG quality `-q:v 2`) plus a `.complete` marker.
- Frame-exact **resume** after pause, stop, crash or power loss; damaged last frames are detected and redone.
- Batch-safe: a corrupted or unsupported file is reported and skipped; the rest continue.
- Disk-space guard, paths with spaces and Unicode characters, live CPU/RAM/GPU/NVDEC/VRAM/disk telemetry.

### Annotation tool
- Image-first canvas (controls never cover the frame), click-to-mark with crosshair.
- States: `VISIBLE`, `PARTIALLY OCCLUDED`, `FULLY OCCLUDED`, `OUT OF BOUNDS`, `SEVERE MOTION BLUR`.
- Keyboard: `←`/`→` ±1 frame, `Shift+←`/`Shift+→` ±10, `Space` play/pause, `Enter` save & next.
- Pages: ANNOTATING, CSV (double-click to jump), RANGES, STATISTICS, SETTINGS.
- `annotations.csv` (`frame,x,y,visibility,x1,y1,x2,y2,source,confidence,status`) is written atomically.

### Tools
- `tracknet-prepper-cli doctor` — dependency and GPU report (also run by the installers).
- `tracknet-prepper-cli extract INPUT OUTPUT [--mode auto|gpu|cpu]` — headless extraction.
- `tracknet-prepper-cli convert-tracknet --input FRAMES --output DATASET [--validation-ratio 0.2] [--copy-images] [--heatmap-format jpg|png]`.

## 📦 Installation

| Platform | Download | Install |
|---|---|---|
| Windows 10 (1809+) / 11, 64-bit | `TrackNetV1_Dataset_Prepper_V2_Setup.exe` | Double-click → follow the wizard → Start menu |
| Windows, no install | `TrackNetV1_Dataset_Prepper_V2_Portable.zip` | Unzip → run `TrackNetPrepper.exe` |
| Ubuntu 24.04 LTS, x86-64 | `tracknet-prepper_2.1.0_amd64.deb` | `sudo apt install ./tracknet-prepper_2.1.0_amd64.deb` |

Neither platform needs Python, pip, the CUDA Toolkit or manual PATH changes.

**Windows** — the installer works without administrator rights (or for all users),
shows a *System check* page (Windows version, NVIDIA GPU and driver, any FFmpeg
already on your PATH — executed and version-checked, not just found), installs the
bundled FFmpeg only when no compatible one exists, and verifies the installation at
the end. Uninstalling never deletes your frames or datasets.
Details: [docs/INSTALLATION_WINDOWS.md](docs/INSTALLATION_WINDOWS.md).

**Ubuntu** — `apt` installs only the missing Qt/X11 libraries and, unless already
present, Ubuntu's `ffmpeg`; the Python runtime is bundled in `/opt/tracknet-prepper`
and your system Python is untouched. Details:
[docs/INSTALLATION_UBUNTU.md](docs/INSTALLATION_UBUNTU.md).

NVIDIA drivers are never bundled or modified by either installer.

## ⚡ GPU acceleration and CPU fallback

| | GPU pipeline | CPU pipeline |
|---|---|---|
| Decode | NVIDIA NVDEC | CPU |
| JPEG encode | CPU | CPU |
| When | AUTO + NVDEC verified, or GPU mode | No working NVDEC, unsupported stream, or CPU mode |

- Needed for GPU decoding: an NVDEC-capable NVIDIA GPU, a working NVIDIA driver,
  and an FFmpeg build with CUDA support (the bundled Windows FFmpeg and Ubuntu's
  `ffmpeg` both qualify). **Not** needed: the CUDA Toolkit.
- The header shows the result: `● NVIDIA NVDEC DECODE VERIFIED`, `● CPU MODE — NVIDIA GPU
  FOUND, NVDEC FAILED` (with the reason under **SYSTEM CHECK**), or `● CPU MODE — NO NVIDIA GPU`.
- Only decoding runs on the GPU, so the speed-up depends on resolution, codec and how
  fast your CPU encodes JPEGs. NVENC is detected and reported but not used — it encodes
  video, not images.
- In Docker, pass `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`.

## 🧭 Workflows

### 1. Video → frames
1. **VIDEO → FRAMES** tab → **SELECT INPUT** (folder; sub-folders included) → **SELECT OUTPUT**.
2. Choose **ACCELERATION** (AUTO is right for almost everyone) → **START EXPORTING**.
3. **PAUSE** / **RESUME**, or **CANCEL** → *Stop & keep* / *Cancel & delete*.
   Closing the app mid-export offers to stop and keep progress; starting the same
   folders again resumes exactly where it stopped.

Same-named videos in different sub-folders get distinct output folders
(`match1__cam`, `match2__cam`).

### 2. Annotate
1. **ANNOTATION TOOL** → **SELECT FRAME DIRECTORY** → pick one video's frame folder.
2. Click the ball (or choose a state first), then **SAVE & NEXT** / `Enter`.
   Fully occluded / out-of-bounds frames need no click.
3. Review in **CSV**, **RANGES** and **STATISTICS**.

### 3. Convert to TrackNet V1
```bash
tracknet-prepper-cli convert-tracknet --input "<output>/<video>" --output "<dataset>" --validation-ratio 0.2 --copy-images
```
Produces `images/`, `heatmaps/`, `training_model1.csv`, `testing_model1.csv` and
`conversion_report.json`. `--heatmap-format png` stores lossless heatmaps (the default
`jpg` matches v2.0 output). From a source checkout: `python tools/convert_to_tracknet.py …`.

## 📊 Benchmarks

BENCHMARK_TABLE_PLACEHOLDER

## 🛠 Troubleshooting

| Symptom | What to do |
|---|---|
| `FFMPEG UNAVAILABLE` | Windows: re-run setup with **Bundled FFmpeg**, or `winget install Gyan.FFmpeg`. Ubuntu: `sudo apt install ffmpeg`. |
| `NVDEC FAILED` | Open **SYSTEM CHECK** for the FFmpeg error; update the NVIDIA driver. On Ubuntu install `libnvidia-decode-<driver>`; in Docker add the `video` capability. AUTO keeps working on the CPU. |
| A video failed | It is listed in the end-of-batch summary (corrupted, truncated, not a video, unsupported codec). Other videos are unaffected. |
| Disk full | The export stops and keeps its frames; free space and resume. |
| SmartScreen warning | The Windows build is not code-signed: *More info → Run anyway*. |
| Logs | **LOGS** button, or `%LOCALAPPDATA%\TrackNetPrepper\logs` / `~/.local/state/tracknet-prepper/logs`. |

## 🧑‍💻 Development

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python app/main.py                 # or: python -m app.main
python -m pytest                   # 89 tests; needs FFmpeg on PATH, GPU tests skip without NVDEC
```

Building releases (see [docs/ARCHITECTURE.md §10](docs/ARCHITECTURE.md#10-packaging-architecture)):

```powershell
# Windows: installer + portable zip + checksums  -> release\
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
powershell -ExecutionPolicy Bypass -File packaging\windows\test_installer.ps1
```
```bash
# Ubuntu 24.04 .deb, built in a clean ubuntu:24.04 container -> release/
bash packaging/linux/docker_build.sh                # USE_GPU=1 to run GPU tests too
docker run --rm -v "$PWD:/src" ubuntu:24.04 bash /src/packaging/linux/test_deb.sh
```

Repository layout:

```
app/                 application package
  main.py, cli.py    GUI and CLI entry points
  ui/                main window, annotation tool, background helpers
  processing/        exporter, worker, resume, scanner, resource manager
  hardware/          capability detection (FFmpeg, NVIDIA, NVDEC/NVENC self-tests)
  tools/             TrackNet converter
  utils/             FFmpeg discovery, paths, logging, subprocess helpers
  resources/         icon, H.264 self-test clip
tests/               pytest suite (synthetic media only)
tools/               converter shim, benchmark, TrackNet assistant (experimental)
packaging/           PyInstaller spec, Windows (Inno Setup) and Linux (.deb) builds
docs/                architecture, installation, release notes, test results
config tests/        historical v1/v2.0 notes and benchmarks
```

Documentation: [Architecture](docs/ARCHITECTURE.md) • [Windows install](docs/INSTALLATION_WINDOWS.md) •
[Ubuntu install](docs/INSTALLATION_UBUNTU.md) • [Release notes](docs/RELEASE_NOTES_V2.md) •
[Test results](docs/TEST_RESULTS.md)

## 🏷️ Release history

- **v2.1.0** (2026-11-18) — V2 stabilization: CPU pipeline and fallback, verified GPU status,
  frame-exact resume, MKV/WebM fix, Windows installer and Ubuntu package.
  [Release notes](docs/RELEASE_NOTES_V2.md)
- **v2.0.0 "Alela Polema"** (2026-08-20) — TrackNet annotation tool, severe-motion-blur state, dual-tab UI.
- **v1.0.0 "On The Way To Burn"** (2026-08-18) — NVDEC frame extraction, resume, job state, telemetry.

## 📄 License

MIT — see [LICENSE](LICENSE). The bundled Windows FFmpeg is distributed under its own
licence, included next to it as `ffmpeg/LICENSE*`.

## 👨‍💻 Author

**Sanjay Kumar S** — Computer Vision & Deep Learning Engineer
[LinkedIn](https://www.linkedin.com/in/sanjaykumarksk/) • [GitHub](https://github.com/Sanjay1712KSK)
