# 🚀 Frame Generator v2.0.0 — "Alela Polema"

**Release Tag:** `v2.0.0`  
**Release Name:** `v2 - Alela Polema`  
**Release Date:** August 20, 2026  
**Target Platform:** Windows 10 / 11 (64-bit)  
**License:** [MIT License](LICENSE)  

---

## 🌟 Executive Summary

We are thrilled to release **Frame Generator v2.0.0 — "Alela Polema"**!

This major release transforms Frame Generator from a standalone GPU video-to-frames extractor into a full-scale **Computer Vision & Sports Analytics Workstation**. It introduces a native **TrackNet Computer Vision Annotation Tool (`AnnotationTab`)** directly embedded into a new dual-tab interface, designed specifically for rapid, micro-precision ball tracking annotation with zero UI occlusions.

---

## 🎯 What's New in v2.0.0 ("Alela Polema")

### 🎯 1. Dedicated TrackNet Computer Vision Annotation Workstation
- **Aspect-Ratio Preserving Viewport (`AnnotationImage`)**: Image-first canvas scaling smoothly to any window dimension without stretching or distorting source frame aspect ratios.
- **Zero-Occlusion Layout**: All controls, frame counters, metrics, and state selectors are placed strictly beneath the image canvas, guaranteeing that no popovers or menus ever obscure ball visibility.
- **Single-Click Center Marking**: Click directly on the ball center in the frame to record `(x, y)` pixel coordinates mapped back to original native frame resolution with visual crosshairs.

### ⚡ 2. 5-State Fine-Grained Ball Visibility System
- `● VISIBLE`: Ball center recorded (`visibility = 1`, `status = ACCEPTED`).
- `◐ PARTIALLY OCCLUDED`: Ball partially visible behind racket/player (`visibility = 1`).
- `✕ FULLY OCCLUDED`: Ball completely hidden (`x = 0, y = 0, visibility = 0`, `status = FULLY_OCCLUDED`).
- `↗ OUT OF BOUNDS`: Ball has exited the court/camera frame (`x = 0, y = 0, visibility = 0`, `status = OUT_OF_BOUNDS`).
- `≈ SEVERE MOTION BLUR`: **(New in v2)** Specifically designed for extreme velocity shots where motion blur stretches the ball into an elongated trail. Clicking the estimated center records `visibility = 1` tagged with `status = SEVERE_MOTION_BLUR`.

### 📑 3. 5-Sub-Page Annotation Architecture
- **`ANNOTATING`**: Full frame workspace with frame scrubbing slider, jump navigation, play/pause sequence preview, current-frame metadata grid, and auto-save toggle.
- **`CSV`**: Real-time synchronized TrackNet dataset table with row double-clicking to jump directly to any frame.
- **`RANGES`**: Contiguous segment summary table detailing rallies, occlusion spans, and out-of-bounds intervals.
- **`STATISTICS`**: 13 real-time metric cards summarizing progress percentage, annotated counts, visibility ratios, blur distribution, and model confidence breakdowns.
- **`SETTINGS`**: AI-assisted semi-automatic tracking configuration supporting **SAM 2.1** (Tiny, Small, Base+, Large) with Docker container integration and confidence thresholds.

### ⌨️ 4. High-Speed Keyboard Navigation
- `←` / `→`: Step backward / forward 1 frame.
- `Shift + ←` / `Shift + →`: Step backward / forward 10 frames.
- `Space`: Toggle 30fps continuous sequence playback.
- `Enter` (in frame box): Jump directly to a specific frame number.
- `SAVE & NEXT ▶`: Save annotation and advance instantly.

### 📐 5. Responsive UI & Clean Project Structure
- Adaptive window initialization dynamically scaling to available monitor dimensions (optimized from laptops up to 27"+ 4K screens).
- Test logs, diagnostics, and build specs moved to clean `config tests/` folder.

---

## ⚡ Instant Quick Start (Pre-Built Executable)

```powershell
# 1. Clone the repository
git clone https://github.com/Ayan-Crafts/Frame-Converter.git
cd Frame-Converter

# 2. Launch the standalone application directly
.\dist\FrameGenerator\FrameGenerator.exe
```

---

# 📦 Release Archive: v1.0.0 — "On The Way To Burn"

**Release Tag:** `v1.0.0`  
**Release Name:** `On The Way To Burn - v1`  
**Release Date:** August 18, 2026  
**License:** [MIT License](LICENSE)  

---

## 🌟 Executive Summary

We are proud to announce the first general availability milestone release of **Frame Generator (v1.0.0 — "On The Way To Burn")**.

Frame Generator is a high-throughput, GPU-accelerated video frame extraction pipeline and desktop workstation tailored specifically to eliminate the massive I/O and decoding bottlenecks inherent in Computer Vision (CV) dataset curation and Deep Learning pipelines.

By unifying low-level **NVIDIA CUDA (NVDEC)** zero-copy hardware decoding with a modern **PySide6 (Qt6)** UI, dynamic system resource profiling, and keyframe-accurate fault-tolerant resuming, Frame Generator allows machine learning engineers and researchers to extract tens of thousands of high-fidelity frames in seconds instead of minutes.

---

## ⚡ Instant Quick Start (Pre-Built Executable)

For end users wanting an immediate, zero-configuration setup without installing Python or FFmpeg dependencies manually:

```powershell
# 1. Clone the repository
git clone https://github.com/Ayan-Crafts/Frame-Converter.git
cd Frame-Converter

# 2. Launch the standalone application directly
.\dist\FrameGenerator\FrameGenerator.exe
```

*The pre-built distribution bundle comes bundled with local hardware-accelerated FFmpeg / FFprobe runtime binaries and the complete PySide6 GUI runtime.*

---

## 🎯 What's Included in v1.0.0

### 🚀 1. Hardware-Accelerated Decoding Engine
- **NVIDIA CUDA & NVDEC Pipeline:** Integrates direct GPU hardware decoding via `ffmpeg -hwaccel cuda -hwaccel_output_format cuda` and `hwdownload,format=nv12` filter graphs.
- **Extreme Extraction Speeds:** Benchmarked at **1,773 FPS (35.5x realtime)** on an NVIDIA RTX 4050, extracting 24,000+ frames in **13.73 seconds**.
- **Multi-Vendor GPU Probing:** Automated hardware detection module (`HardwareDetector`) that queries NVIDIA GPUs via `nvidia-smi` (VRAM, driver version, clock utilization) and AMD GPUs via Windows WMIC, with automatic CPU multi-core fallback.
- **Configurable Frame Quality:** Produces clean, zero-padded image sequences (`%06d.jpg`) with studio-grade JPEG compression (`-q:v 2`) or lossless outputs.

### 🖥️ 2. Modern PySide6 Desktop Workstation
- **Interactive Qt6 GUI:** A dark-themed, responsive dashboard designed for high-density monitoring and batch processing.
- **Live Stat Cards:** Real-time cards displaying:
  - Total Extracted Frames
  - Instantaneous Decoding FPS
  - Speed Multiplier (e.g., `35.5x`)
  - Elapsed Time & Dynamic ETA Calculation
- **Hardware Telemetry Integration:** Live gauges tracking GPU Core Utilization, VRAM Consumption, GPU Temperature, Host CPU Load, and System Memory.
- **Asynchronous Architecture:** Fully decoupled multi-threaded processing via `QThread` (`ExportWorker`) to guarantee an unblocked, 60fps UI experience during massive multi-gigabyte jobs.

### 🔄 3. Smart Keyframe Resuming & Fault Tolerance
- **Automated Directory Inspection:** Inspects destination folders to calculate existing frame numbers before initiating extraction.
- **Keyframe-Accurate Seek Alignment:** Combines backward keyframe seeking (`-ss`) with precise frame discard filters (`select='gte(n,X)'`) to guarantee zero duplicate or missing frames when resuming interrupted jobs.
- **Batch Skip Markers:** Generates lightweight `.complete` tracking files to rapidly skip already-completed videos during recursive batch processing.

### 🧠 4. Dynamic Resource & Thermal Profiling (`ResourceManager`)
- **System-Aware Adaptation:** Dynamically calculates optimal FFmpeg worker threads and buffer allocations based on available GPU VRAM and physical CPU cores.
- **Memory & Thermal Protection:** Automatically limits resource allocation under heavy workloads to prevent system instability, memory overflow, or thermal throttling.

### 🗂️ 5. Persistent Job Queue State Machine (`JobManager`)
- **Structured JSON Logging:** Maintains persistent job logs and state histories inside `~/.frame-generator/jobs/`.
- **Full Lifecycle Controls:** User-driven state controls for:
  - **Start:** Launches batch pipeline.
  - **Pause / Resume:** Pauses FFmpeg subprocess and resumes from exact frame index.
  - **Stop (Keep):** Gracefully terminates execution while preserving all extracted frames.
  - **Cancel (Clean):** Terminates FFmpeg and performs directory cleanup of partial runs.

---

## 📊 Benchmark Verification

The following verified benchmarks were recorded during testing on standard consumer mobile hardware:

| Benchmark Parameter | Test Value |
| :--- | :--- |
| **Input Source File** | `squash 8 min.mp4` (H.264 / AAC, 1280x720 @ 50.0 FPS) |
| **Video Duration** | 08:07.04 (487.04 seconds) |
| **Total Frames Extracted** | **24,352 frames** |
| **Total Processing Time** | **13.73 seconds** |
| **Average Extraction Speed** | **1,773.0 FPS** |
| **Realtime Speedup** | **35.5x Realtime** |
| **GPU VRAM Utilization** | ~129 MiB / 6141 MiB (~2.1%) |
| **GPU Core Temperature** | 54.0°C (Stable under continuous load) |
| **Tested Hardware** | NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM, Driver 610.88, CUDA 13.3) |

---

## 💻 Running from Source (Developer Setup)

```powershell
# 1. Clone repository
git clone https://github.com/Ayan-Crafts/Frame-Converter.git
cd Frame-Converter

# 2. Setup Python virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install PySide6 psutil

# 4. Verify local CUDA support in FFmpeg
ffmpeg -hide_banner -hwaccels

# 5. Launch the application
python app/main.py
```

---

## 🛡️ Repository Integrity & File Policies

- Added comprehensive `.gitignore` rules preventing media assets (`.mp4`, `.mov`, `.avi`, `.mkv`), frame directories (`output/`, `Datasets/`, `benchmark_frames/`), binary executables, build folders (`build/`, `dist/`), and virtual environments (`.venv/`) from exceeding GitHub's 100MB file limit.

---

## 🗺️ What's Next in the Roadmap

- [ ] AI-Powered Blur and Duplicate Frame Pruning (Laplacian variance & pHash).
- [ ] Direct annotation format exporters (YOLO `.txt`, COCO `.json`, Pascal VOC `.xml`).
- [ ] Multi-GPU parallel stream distribution for multi-video datasets.
- [ ] Embedded video preview player with visual timeline segment trimming.

---

## 👨‍💻 Author & Maintainer

- **Lead Developer:** Sanjay Kumar S
- **GitHub:** [@Sanjay1712KSK](https://github.com/Sanjay1712KSK)
- **LinkedIn:** [Sanjay Kumar S](https://www.linkedin.com/in/sanjaykumarksk/)
