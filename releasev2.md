# 🚀 Frame Generator v2.0.0 — "Alela Polema"

**Release Tag:** `v2.0.0`  
**Release Name:** `v2 - Alela Polema`  
**Release Date:** August 20, 2026  
**Target Platform:** Windows 10 / 11 (64-bit)  
**License:** [MIT License](LICENSE)  

---

## 🌟 Executive Summary

We are excited to announce the official release of **Frame Generator v2.0.0 ("Alela Polema")**!

This major release elevates Frame Generator from a high-throughput GPU frame extraction utility into a comprehensive **Computer Vision & Sports Analytics Workstation**. It introduces the native **TrackNet Computer Vision Annotation Tool (`AnnotationTab`)** inside a modern dual-tab desktop interface, custom-engineered for rapid, micro-precision ball tracking annotation with zero UI occlusions.

---

## ⚡ Instant Quick Start (Pre-Built Standalone App)

No Python setup or manual dependency installation is required! You can directly launch the pre-compiled standalone executable:

```powershell
# 1. Clone the repository
git clone https://github.com/Ayan-Crafts/Frame-Converter.git
cd Frame-Converter

# 2. Launch the standalone application
.\dist\FrameGenerator\FrameGenerator.exe
```

*The pre-built package includes embedded FFmpeg/FFprobe hardware-accelerated binaries and the full PySide6 runtime.*

---

## 🎯 What's New in v2.0.0 ("Alela Polema")

### 🎯 1. Dedicated TrackNet Computer Vision Annotation Workstation
- **Aspect-Ratio Preserving Canvas (`AnnotationImage`)**: Image-first frame viewport that scales smoothly to any window dimension without stretching or distorting source frame aspect ratios.
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
- Test logs, diagnostics, and build specs moved to a clean `config tests/` folder.

---

## 💻 Running from Source (Developer Setup)

```powershell
# 1. Clone the repository
git clone https://github.com/Ayan-Crafts/Frame-Converter.git
cd Frame-Converter

# 2. Setup Python virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install PySide6 psutil

# 4. Launch the application
python app/main.py
```

---

## 🛠️ System Requirements
- **OS**: Windows 10 / 11 (64-bit)
- **GPU**: NVIDIA GPU with CUDA driver support (Driver 520+) or AMD/Intel GPU / Multi-core CPU fallback.
- **Python (Optional for source run)**: Python 3.9 to 3.14.

---

## 👨‍💻 Developer & Author
- **Lead Developer**: Sanjay Kumar S
- **GitHub**: [@Sanjay1712KSK](https://github.com/Sanjay1712KSK)
- **LinkedIn**: [Sanjay Kumar S](https://www.linkedin.com/in/sanjaykumarksk/)
- **License**: [MIT License](LICENSE)
