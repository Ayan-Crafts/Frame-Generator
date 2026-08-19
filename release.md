# 🚀 Frame Generator v1.0.0 — "On The Way To Burn"

**Release Tag:** `v1.0.0`  
**Release Name:** `On The Way To Burn - v1`  
**Release Date:** August 18, 2026  
**Target Platform:** Windows 10 / 11 (64-bit)  
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
