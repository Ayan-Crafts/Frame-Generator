#!/usr/bin/env bash
# Installation test for the .deb. Run as root in a FRESH ubuntu:24.04
# container (nothing pre-installed), e.g.:
#
#   docker run --rm -v "$PWD:/src" ubuntu:24.04 bash /src/packaging/linux/test_deb.sh
#   docker run --rm --gpus all -v "$PWD:/src" ubuntu:24.04 bash /src/packaging/linux/test_deb.sh
#
# Scenarios
#   A. apt install --no-install-recommends (no FFmpeg)  -> app installs, doctor
#      reports FFmpeg missing with exit 3, GUI still starts
#   B. apt install ffmpeg afterwards                     -> existing install reused
#   C. extraction via CLI (auto + cpu), frame counts checked against ffprobe
#   D. GUI launch under Xvfb (window screenshot), .desktop entry and icon
#   E. remove -> /opt gone, user data kept; purge; reinstall (with Recommends)
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
SRC="${SRC:-/src}"
DEB="$(ls -1 "$SRC"/release/tracknet-prepper_*_amd64.deb | sort -V | tail -n1)"
RESULTS="${RESULTS:-$SRC/release/linux-test-results}"
mkdir -p "$RESULTS"
PASS=0; FAIL=0
log() { printf '%s\n' "$*" | tee -a "$RESULTS/summary.txt"; }
ok()  { PASS=$((PASS+1)); log "PASS  $*"; }
bad() { FAIL=$((FAIL+1)); log "FAIL  $*"; }
check() { local name="$1"; shift; if "$@" >>"$RESULTS/details.log" 2>&1; then ok "$name"; else bad "$name"; fi; }

: > "$RESULTS/summary.txt"; : > "$RESULTS/details.log"
. /etc/os-release
log "Test host: $PRETTY_NAME $(uname -m) | package: $(basename "$DEB")"
log "GPU device nodes: $(ls /dev/nvidia* /dev/dxg 2>/dev/null | tr '\n' ' ' || true)"

apt-get update -qq >>"$RESULTS/details.log" 2>&1

# ---------------------------------------------------------------- A
log "--- A: install without recommends (no FFmpeg on the system)"
check "A1 apt install ./deb --no-install-recommends" \
  apt-get install -y -qq --no-install-recommends "$DEB"
check "A2 ffmpeg NOT installed" sh -c '! command -v ffmpeg'
check "A3 launchers present" test -x /usr/bin/tracknet-prepper -a -x /usr/bin/tracknet-prepper-cli
tracknet-prepper-cli doctor >"$RESULTS/doctor-no-ffmpeg.txt" 2>&1; code=$?
if [ "$code" = 3 ] && grep -q "apt install ffmpeg" "$RESULTS/doctor-no-ffmpeg.txt"; then
  ok "A4 doctor reports missing FFmpeg (exit 3, actionable hint)"
else
  bad "A4 doctor without FFmpeg (exit $code)"
fi
check "A5 version" tracknet-prepper-cli --version

# ---------------------------------------------------------------- B
log "--- B: install FFmpeg afterwards (dependency installed by apt, then reused)"
check "B1 apt install ffmpeg" apt-get install -y -qq --no-install-recommends ffmpeg
log "      FFmpeg: $(ffmpeg -version | head -n1)"
tracknet-prepper-cli doctor >"$RESULTS/doctor.txt" 2>&1; code=$?
cat "$RESULTS/doctor.txt" >>"$RESULTS/details.log"
if [ "$code" = 0 ] && grep -q "(system)" "$RESULTS/doctor.txt"; then
  ok "B2 doctor finds system FFmpeg"
else
  bad "B2 doctor with FFmpeg (exit $code)"
fi
tracknet-prepper-cli doctor --json "$RESULTS/doctor.json" >/dev/null 2>&1
grep -E "NVIDIA|NVDEC|NVENC|Auto mode" "$RESULTS/doctor.txt" | sed 's/^/      /' | tee -a "$RESULTS/summary.txt"

# ---------------------------------------------------------------- C
log "--- C: frame extraction"
MEDIA=/tmp/media; OUTD=/tmp/frames
mkdir -p "$MEDIA/sub dir"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=1280x720:rate=50 -t 6 -c:v libx264 -pix_fmt yuv420p "$MEDIA/h264 720p.mp4"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=640x360:rate=30 -t 3 -c:v libx265 -pix_fmt yuv420p "$MEDIA/sub dir/hevc.mkv"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=640x360:rate=25 -t 3 -c:v libvpx-vp9 -b:v 300k "$MEDIA/vp9 clip.webm"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=640x360:rate=30 -t 2 -c:v libx264 -pix_fmt yuv444p "$MEDIA/h264_444.mp4"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=320x240:rate=25 -t 2 -c:v libx264 -pix_fmt yuv420p "$MEDIA/unicode vidéo 测试.mp4"
printf 'not a video' > "$MEDIA/broken.mp4"

for mode in auto cpu; do
  rm -rf "$OUTD"
  tracknet-prepper-cli extract "$MEDIA" "$OUTD" --mode "$mode" --json "$RESULTS/extract-$mode.json" \
    >"$RESULTS/extract-$mode.txt" 2>&1; code=$?
  [ "$code" = 1 ] && ok "C1[$mode] extract finished; broken.mp4 reported as failed (exit 1)" || bad "C1[$mode] extract exit $code"
  all_ok=1
  for v in "h264 720p" "hevc" "vp9 clip" "h264_444" "unicode vidéo 测试"; do
    src="$(find "$MEDIA" -name "$v.*" | head -n1)"
    expected="$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$src")"
    got="$(ls "$OUTD/$v"/*.jpg 2>/dev/null | wc -l)"
    if [ "$got" = "$expected" ] && [ -f "$OUTD/$v/.complete" ]; then
      log "      [$mode] $v: $got/$expected frames"
    else
      log "      [$mode] $v: MISMATCH got $got expected $expected"; all_ok=0
    fi
  done
  [ "$all_ok" = 1 ] && ok "C2[$mode] frame counts match ffprobe" || bad "C2[$mode] frame counts"
  grep -E "OK in|FAILED|WARNING" "$RESULTS/extract-$mode.txt" | sed 's/^/      /' >>"$RESULTS/summary.txt"
done

# ---------------------------------------------------------------- D
log "--- D: GUI and desktop integration"
apt-get install -y -qq --no-install-recommends xvfb xauth desktop-file-utils >>"$RESULTS/details.log" 2>&1
check "D1 .desktop entry valid" desktop-file-validate /usr/share/applications/tracknet-prepper.desktop
check "D2 icon installed" test -s /usr/share/icons/hicolor/256x256/apps/tracknet-prepper.png
check "D3 Exec target resolves" sh -c 'command -v "$(sed -n "s/^Exec=\([^ ]*\).*/\1/p" /usr/share/applications/tracknet-prepper.desktop)"'
missing="$(find /opt/tracknet-prepper -name '*.so*' -exec ldd {} \; 2>/dev/null | grep 'not found' | sort -u)"
if [ -z "$missing" ]; then ok "D4 all bundled libraries resolve (ldd)"; else bad "D4 unresolved libraries: $missing"; fi
xvfb-run -a -s "-screen 0 1600x1000x24" tracknet-prepper --smoke-test 8 \
  --screenshot "$RESULTS/linux-window.png" >"$RESULTS/gui.txt" 2>&1; code=$?
[ "$code" = 0 ] && [ -s "$RESULTS/linux-window.png" ] && ok "D5 GUI starts under X11 (xcb) and renders" || bad "D5 GUI smoke test exit $code"
LOGFILE="$HOME/.local/state/tracknet-prepper/logs/tracknet-prepper.log"
check "D6 log file written" test -s "$LOGFILE"
grep -q "platform plugin: xcb" "$LOGFILE" && ok "D7 Qt xcb platform plugin used" || bad "D7 platform plugin"

# ---------------------------------------------------------------- E
log "--- E: uninstall / reinstall"
mkdir -p /tmp/dataset-keep && cp -r "$OUTD/hevc" /tmp/dataset-keep/
check "E1 apt remove" apt-get remove -y -qq tracknet-prepper
check "E2 /opt/tracknet-prepper removed" sh -c '! test -e /opt/tracknet-prepper'
check "E3 launchers removed" sh -c '! test -e /usr/bin/tracknet-prepper'
check "E4 user logs kept" test -s "$LOGFILE"
check "E5 extracted frames kept" test -f "$OUTD/hevc/.complete"
check "E6 ffmpeg kept (not owned by package)" sh -c 'command -v ffmpeg'
check "E7 purge" apt-get purge -y -qq tracknet-prepper
check "E8 reinstall (with Recommends)" apt-get install -y -qq "$DEB"
check "E9 doctor after reinstall" tracknet-prepper-cli doctor
check "E10 dpkg status installed" sh -c 'dpkg -s tracknet-prepper | grep -q "Status: install ok installed"'

log "--- RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
