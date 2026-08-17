# Frame-Generator

**Open‑Source Project** – This repository is released under the MIT License and serves as a supporting component for a larger computer‑vision application. Its primary role is to provide reliable, GPU‑accelerated frame extraction that downstream vision pipelines can consume.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Data Sources](#data-sources)
- [Benchmark & Test Logs](#benchmark--test-logs)
- [Screenshots](#screenshots)
- [Contributing](#contributing)
- [License](#license)
- [Gitignore](#gitignore)
- [Vision & Future Roadmap](#vision--future-roadmap)
- [Developer Credits](#developer-credits)
- [About Me](#about-me)

---

## Features

- GPU‑accelerated frame extraction via CUDA (`ffmpeg -hwaccel cuda`).
- Simple command‑line interface for quick testing.
- Benchmark scripts to evaluate decoding/encoding performance.
- Organized dataset folder for easy addition of new videos.

---

## Prerequisites

- **FFmpeg** (full build) – see [ffmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- **NVIDIA Video Codec SDK** for CUDA acceleration – see [NVIDIA SDK](https://developer.nvidia.com/video-codec-sdk#section-get-started)
- Python 3.9+ (optional, for future extensions)
- Windows 10/11 with GPU drivers supporting CUDA.

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/frame-generator.git
   cd frame-generator
   ```
2. Ensure `ffmpeg.exe` is on your `PATH` or place it inside the project root.
3. (Optional) Create a virtual environment for any Python scripts:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

---

## Usage

A basic command to extract frames from a video using CUDA acceleration:

```bash
ffmpeg -hide_banner -hwaccel cuda -hwaccel_output_format cuda -i "Datasets/<your‑video>.mp4" -vf "fps=1" "output/frame_%04d.png"
```

The `benchmark_frames/` directory contains example scripts that run the above command and log performance metrics (see **Benchmark & Test Logs** below).

---

## Data Sources

The `sources.txt` file lists all external resources used for testing and benchmarking:

```
https://www.gyan.dev/ffmpeg/builds/
https://developer.nvidia.com/video-codec-sdk#section-get-started
YouTube links for sample videos:
- https://www.youtube.com/watch?v=0H9xNZQhEc4
- https://www.youtube.com/watch?v=ZfO5MT5X410
- https://www.youtube.com/watch?v=7pWKCFJSQpo
- https://www.youtube.com/watch?v=yMKDa4aHMsk
- https://www.youtube.com/watch?v=RN78Es4BSpk
```

Feel free to add additional sources as needed.

---

## Benchmark & Test Logs

- **ffmpegstats.txt** – Output of `ffmpeg -version` and hardware acceleration capabilities on the host machine.
- **ffmpegtest.txt** – Sample run extracting frames from `squash 8 min.mp4` with detailed timing and GPU usage logs.
- **test.txt** – Simple command used for a quick null‑output test.

These files are included in the repository for reference and can be consulted to reproduce the performance environment.

---

## Screenshots

> **[Placeholder for application screenshots – to be added later]**

---

## Contributing

Contributions are welcome! Please fork the repository, create a feature branch, and submit a pull request. Ensure that any new files adhere to the `.gitignore` rules (see below).

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Gitignore

The repository now ignores common sensitive and system files, including:

```
# Sensitive files that should never be committed to a public repository
.env
*.pem
*.key
*.crt
*.p12
*.pfx
id_rsa
id_dsa
*.asc
# OS generated files
.DS_Store
Thumbs.db
```

Feel free to extend this list as your workflow evolves.

---

## Vision & Future Roadmap

- **Current**: Extract frames from video sources using FFmpeg with optional CUDA acceleration.
- **Upcoming**: Enhance functionality and UI to meet the evolving needs of the main computer‑vision project (e.g., configurable extraction parameters, visual progress dashboard, integration with annotation tools).

---

## Developer Credits

- **Primary Author**: Sanjay Kumar S – Concept, implementation, and ongoing maintenance.

---

## About Me

- **Name**: Sanjay Kumar S
- **LinkedIn**: [Sanjay Kumar | LinkedIn](https://www.linkedin.com/in/sanjaykumarksk/)
- **GitHub**: [Sanjay1712KSK (Sanjay Kumar S)](https://github.com/Sanjay1712KSK)