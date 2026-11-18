# Installing on Windows

Supported: 64-bit Windows 10 (version 1809 or newer) and Windows 11.
No Python, pip, CUDA toolkit or PATH changes are needed.

## 1. Installer (recommended)

1. Download `TrackNetV1_Dataset_Prepper_V2_Setup.exe` and, optionally,
   `SHA256SUMS-windows.txt` to verify it:
   ```powershell
   Get-FileHash .\TrackNetV1_Dataset_Prepper_V2_Setup.exe -Algorithm SHA256
   ```
2. Double-click the installer. The build is not code-signed, so Windows
   SmartScreen may show "Windows protected your PC": choose **More info →
   Run anyway**.
3. Choose **Install for me only** (no administrator rights needed; installs to
   `%LOCALAPPDATA%\Programs\TrackNetV1 Dataset Prepper`) or **Install for all
   users** (asks for administrator rights; installs to `Program Files`).
4. **System check page** — setup shows what it found:
   * Windows version.
   * NVIDIA GPU name and driver version (from `nvidia-smi`), or that none was found.
   * Any FFmpeg already on your `PATH`: it is *run* to read its version and to
     check for CUDA support; a file merely existing is not trusted.
5. **Components page** — "Bundled FFmpeg" is pre-selected only when no
   compatible FFmpeg (5.1+ with CUDA) was found. If you already have one, it
   is left unselected and the app reuses yours. You can override either way.
6. Optionally tick **Create a desktop shortcut**.
7. At the end, setup runs `tracknet-prepper-cli doctor` to verify the
   installation (FFmpeg works, GPU decode test) and saves the result to
   `%LOCALAPPDATA%\TrackNetPrepper\install-check.json`. If no usable FFmpeg
   is available it tells you how to fix it.
8. Launch from the Start menu (**TrackNetV1 Dataset Prepper**) or the desktop.

### Repair / upgrade

Run the same (or a newer) installer again. It installs over the existing
copy, keeps your component choices, and closes the app first if it is open.
Deselecting "Bundled FFmpeg" on a re-run removes the bundled copy.

### Uninstall

*Settings → Apps → TrackNetV1 Dataset Prepper → Uninstall*, or the
**Uninstall** shortcut in the Start menu folder.

* The application folder is removed.
* You are asked whether to also delete logs and job history
  (`%LOCALAPPDATA%\TrackNetPrepper`, `%USERPROFILE%\.frame-generator`).
  The default is **No**.
* Extracted frames, `annotations.csv` files and datasets are **never**
  deleted — they live in the folders you chose, never in the install folder.

## 2. Portable zip

`TrackNetV1_Dataset_Prepper_V2_Portable.zip` contains the same application
with FFmpeg included. Unzip anywhere (including a USB drive) and run
`TrackNetPrepper.exe`. Nothing is registered; delete the folder to remove it.

Limitations: no Start-menu entry or uninstaller; no automatic reuse of an
existing FFmpeg (the bundled one is used, falling back to `PATH` only if the
`ffmpeg` folder is deleted); logs still go to `%LOCALAPPDATA%\TrackNetPrepper`.

## 3. First launch

The header shows the acceleration status after a 1–3 s background check:

| Header | Meaning |
|---|---|
| `● NVIDIA NVDEC DECODE VERIFIED` (green) | A real H.264 test clip was decoded on the GPU through the extraction pipeline. AUTO mode uses the GPU. |
| `● CPU MODE — NVIDIA GPU FOUND, NVDEC FAILED` (amber) | A GPU exists, but GPU decoding does not work with this driver/FFmpeg. Click **SYSTEM CHECK** for the reason. |
| `● CPU MODE — NO NVIDIA GPU` | Extraction runs on the CPU. |
| `● FFMPEG UNAVAILABLE — EXTRACTION DISABLED` (red) | No usable FFmpeg. The annotation tool still works. |

**SYSTEM CHECK** shows the full report (FFmpeg path/version/source, GPU,
driver, CUDA driver API, NVDEC/NVENC test results) and can copy it.
**LOGS** opens the log folder.

## 4. GPU compatibility

* Required: an NVIDIA GPU with NVDEC (GeForce GTX 600 series / Kepler or
  newer) and a current NVIDIA driver. Install or update the driver from
  NVIDIA; the installer never installs or changes drivers.
* Not required: the CUDA Toolkit. FFmpeg loads NVDEC from the driver.
* Codec support depends on the GPU generation (e.g. AV1 decode needs RTX 30
  series or newer; no generation decodes H.264 4:4:4). In AUTO mode, a video
  the GPU cannot decode automatically continues on the CPU, and the
  **Pipeline** line under CURRENT VIDEO shows which was used.
* Only *decoding* runs on the GPU. JPEG encoding always runs on the CPU, so
  the speed-up depends on the CPU too (see `docs/TEST_RESULTS.md`).
* AMD and Intel GPUs are shown but have no accelerated pipeline; the CPU is used.

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| SmartScreen blocks the installer | More info → Run anyway (unsigned build). |
| "FFmpeg unavailable" | Re-run setup and select **Bundled FFmpeg**, or install FFmpeg 5.1+ (`winget install Gyan.FFmpeg`) and restart the app. |
| NVDEC FAILED | Update the NVIDIA driver; check SYSTEM CHECK for the FFmpeg error. Use AUTO or CPU mode meanwhile. |
| A video "could not be read" | The file is corrupted, incomplete or not a video; the rest of the batch continues and a summary is shown at the end. |
| Export stopped: disk almost full | Free space and press RESUME (or START again with the same folders). |
| Need to report a problem | Attach `%LOCALAPPDATA%\TrackNetPrepper\logs\tracknet-prepper.log` and the SYSTEM CHECK text. |
| Use a specific FFmpeg | Set `TNP_FFMPEG` and `TNP_FFPROBE` (full paths) before starting the app. |

## 6. Manual test checklist (clean machine)

Run on a Windows VM/PC that has never had the app installed. Record results
in `docs/TEST_RESULTS.md`.

1. No FFmpeg on PATH, no NVIDIA driver → System check page says so; bundled
   FFmpeg pre-selected; app starts in CPU MODE; extract a video.
2. Compatible FFmpeg with CUDA on PATH → bundled FFmpeg *not* pre-selected;
   after install, SYSTEM CHECK shows `(system)` FFmpeg.
3. NVIDIA GPU with driver → header shows NVDEC VERIFIED; extraction pipeline
   line shows `GPU decode (NVDEC) → CPU JPEG encode`.
4. Install without admin (per-user) and with admin (all users).
5. Paths with spaces and non-ASCII characters (input, output, install dir).
6. Pause → Resume; Stop & keep → Start again; Cancel & delete.
7. Annotation: open a frame folder, click/arrow keys/space, save, reopen.
8. Re-run installer (repair); uninstall with "No" → frames and logs remain;
   uninstall with "Yes" → logs removed, frames remain.
