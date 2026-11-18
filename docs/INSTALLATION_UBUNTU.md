# Installing on Ubuntu 24.04

Package: `tracknet-prepper_<version>_amd64.deb` (x86-64, Ubuntu 24.04 LTS or
newer Debian-based systems with glibc ≥ 2.39).

The Python runtime and Qt are bundled under `/opt/tracknet-prepper`; your
system Python is not used or modified. Everything else comes from Ubuntu via
apt, which reuses what is already installed and installs only what is missing.

## 1. Install

```bash
sudo apt update
sudo apt install ./tracknet-prepper_2.1.0_amd64.deb
```

Use `apt` (not `dpkg -i`) so dependencies are resolved. apt will:

* install any missing Qt/X11 runtime libraries (`Depends`), and
* install Ubuntu's `ffmpeg` package unless it is already present
  (`Recommends`, installed by default). An existing apt FFmpeg is reused.

If you build or manage FFmpeg yourself (e.g. a CUDA-enabled build in
`/usr/local/bin`), install without it and the app will use the `ffmpeg` on
your `PATH`:

```bash
sudo apt install --no-install-recommends ./tracknet-prepper_2.1.0_amd64.deb
```

After installation the package runs a check. Actual output from the test
system (Ubuntu 24.04 container with GPU access):

```
TrackNetV1 Dataset Prepper: checking FFmpeg and NVIDIA GPU support...
TrackNetV1 Dataset Prepper 2.1.0
------------------------------------------------------------
OS: Linux Ubuntu 24.04.5 LTS (x86_64)
CPU threads: 12   RAM: 7.6 GB
FFmpeg: 6.1.1-3ubuntu5 (system) - /usr/bin/ffmpeg
NVIDIA GPU 0: NVIDIA GeForce RTX 4050 Laptop GPU (6141 MiB, compute 8.9)
NVIDIA driver: 621.24   CUDA driver API: 13.5
FFmpeg CUDA hwaccel compiled in: yes
NVDEC frame-extraction pipeline: VERIFIED (H.264 test clip decoded on GPU)
NVENC encoder (not used by extraction): VERIFIED (H.264 test encode succeeded)
Extraction pipeline in Auto mode: GPU decode (NVDEC) → CPU JPEG encode
```

Installed with `--no-install-recommends` and no FFmpeg, it reports
`FFmpeg: NOT AVAILABLE - ffmpeg was not found. Install it with: sudo apt install ffmpeg`,
`Extraction pipeline in Auto mode: CPU decode → CPU JPEG encode`, and the
installation still succeeds (the annotation tool works without FFmpeg).

## 2. Launch

* Application menu: **TrackNetV1 Dataset Prepper**.
* Terminal: `tracknet-prepper`
* Command-line tools: `tracknet-prepper-cli doctor | extract | convert-tracknet`

Works on X11 and Wayland sessions (Qt's xcb plugin via XWayland is the
tested path). Logs: `~/.local/state/tracknet-prepper/logs/`.

## 3. FFmpeg

* Minimum version 5.1 (Ubuntu 24.04 ships 6.1.1, which includes NVDEC/CUDA
  support).
* Resolution order: `TNP_FFMPEG`/`TNP_FFPROBE` → bundled copy (none in the
  .deb) → `PATH`.
* `tracknet-prepper-cli doctor` shows which FFmpeg is used and what it supports.

## 4. NVIDIA GPU

The package never installs or changes NVIDIA drivers. To enable GPU decoding:

```bash
sudo ubuntu-drivers install          # or: sudo apt install nvidia-driver-<version>
sudo reboot
tracknet-prepper-cli doctor          # NVDEC ... VERIFIED
```

The NVIDIA driver metapackage includes `libnvidia-decode-<version>`, which
provides `libnvcuvid.so.1` (NVDEC). If the doctor reports *"Cannot load
libnvcuvid.so.1"*, install that package for your driver version.

The CUDA Toolkit is **not** required.

### Docker / containers

GPU access inside a container needs the NVIDIA container runtime **and** the
`video` driver capability (Docker's default `compute,utility` omits the NVDEC
library):

```bash
docker run --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video ...
```

Without it the app detects the GPU, reports `NVDEC FAILED (Cannot load
libnvcuvid.so.1)` with this hint, and uses the CPU.

## 5. CPU fallback

Without a usable NVIDIA GPU (or with a stream the GPU cannot decode) the CPU
pipeline is used automatically; select **CPU only** in the ACCELERATION menu
to force it. It produces the same frames, more slowly.

## 6. Uninstall

```bash
sudo apt remove tracknet-prepper      # removes /opt/tracknet-prepper and launchers
sudo apt purge tracknet-prepper       # same; nothing system-wide is left
sudo apt autoremove                   # optional: drop now-unused dependencies (e.g. ffmpeg)
```

Per-user data is never deleted by the package: logs
(`~/.local/state/tracknet-prepper`), job history (`~/.frame-generator`),
and all extracted frames, annotations and datasets. Remove them manually if
you want to.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Install with `apt install ./…deb` (not `dpkg -i`) so the X11 libraries are pulled in, or `sudo apt -f install`. |
| No window on a headless server | Use `tracknet-prepper-cli extract …`, or `xvfb-run tracknet-prepper`. |
| NVDEC FAILED | See §4; run `nvidia-smi` to confirm the driver works. |
| FFmpeg unavailable | `sudo apt install ffmpeg` |
