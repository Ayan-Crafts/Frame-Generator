#!/usr/bin/env bash
# Build the Ubuntu 24.04 .deb inside a clean ubuntu:24.04 container.
#
# Normally invoked through packaging/linux/docker_build.sh (or .ps1), which
# mounts the repository at /src. Can also run directly on Ubuntu 24.04.
#
#   SRC=/src  OUT=/src/release  SKIP_TESTS=0  bash packaging/linux/build_linux.sh
#
# Steps: apt build deps -> isolated venv (/build/venv) -> tests -> PyInstaller
# -> .deb assembly (dpkg-deb) -> package lint (desktop file) -> checksums.
set -euo pipefail

SRC="${SRC:-$(cd "$(dirname "$0")/../.." && pwd)}"
OUT="${OUT:-$SRC/release}"
WORK="${WORK:-/build}"
SKIP_TESTS="${SKIP_TESTS:-0}"
export DEBIAN_FRONTEND=noninteractive

step() { printf '\n=== %s ===\n' "$*"; }

step "Build dependencies"
if [ "$(id -u)" = 0 ]; then
  apt-get update -qq
  # binutils: PyInstaller's ELF analysis. Qt/X libs: needed by the tests
  # (offscreen Qt) - not by the build itself. ffmpeg: test media + tests.
  apt-get install -y -qq --no-install-recommends \
    python3 python3-venv python3-pip libpython3.12t64 binutils dpkg-dev desktop-file-utils \
    ffmpeg ca-certificates \
    libegl1 libgl1 libfontconfig1 libdbus-1-3 libglib2.0-0t64 libxkbcommon0 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
    libx11-xcb1 >/dev/null
fi
. /etc/os-release
echo "Building on $PRETTY_NAME ($(uname -m))"

VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SRC/app/__init__.py")"
[ -n "$VERSION" ] || { echo "Cannot read APP_VERSION"; exit 1; }
echo "Version $VERSION"

step "Source copy"
# Build from a copy: keeps root-owned build artefacts out of the mounted
# checkout and avoids slow bind-mounted I/O on Docker Desktop.
rm -rf "$WORK/src"
mkdir -p "$WORK/src"
tar -C "$SRC" --exclude=.git --exclude=.venv --exclude=build --exclude=dist \
    --exclude=release --exclude='__pycache__' -cf - . | tar -C "$WORK/src" -xf -
cd "$WORK/src"

step "Python environment"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip
"$WORK/venv/bin/pip" install --quiet -r requirements-dev.txt
"$WORK/venv/bin/python" -c "import sys, PySide6, PIL, psutil; print('Python', sys.version.split()[0], '| PySide6', PySide6.__version__, '| Pillow', PIL.__version__, '| psutil', psutil.__version__)"

if [ "$SKIP_TESTS" != 1 ]; then
  step "Test suite"
  QT_QPA_PLATFORM=offscreen "$WORK/venv/bin/python" -m pytest -q -p no:cacheprovider \
    --basetemp "$WORK/pytest-tmp"
fi

step "PyInstaller"
"$WORK/venv/bin/python" -m PyInstaller --noconfirm --clean \
  --distpath "$WORK/dist" --workpath "$WORK/pyinstaller" \
  packaging/pyinstaller/tracknet_prepper.spec

step "Assemble .deb"
PKG="$WORK/pkg"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/tracknet-prepper"
cp -a "$WORK/dist/TrackNetPrepper" "$PKG/opt/tracknet-prepper"

for name in tracknet-prepper tracknet-prepper-cli; do
  printf '#!/bin/sh\nexec /opt/tracknet-prepper/%s "$@"\n' "$name" > "$PKG/usr/bin/$name"
  chmod 0755 "$PKG/usr/bin/$name"
done

install -m 0644 packaging/linux/tracknet-prepper.desktop "$PKG/usr/share/applications/"
install -m 0644 app/resources/icon.png "$PKG/usr/share/icons/hicolor/256x256/apps/tracknet-prepper.png"
install -m 0644 LICENSE "$PKG/usr/share/doc/tracknet-prepper/copyright"

INSTALLED_KB="$(du -sk "$PKG" | cut -f1)"
sed -e "s/@VERSION@/$VERSION/" -e "s/@INSTALLED_SIZE@/$INSTALLED_KB/" \
    packaging/linux/debian/control.in > "$PKG/DEBIAN/control"
install -m 0755 packaging/linux/debian/postinst "$PKG/DEBIAN/postinst"
install -m 0755 packaging/linux/debian/postrm "$PKG/DEBIAN/postrm"

# Normalise permissions (files created on a Windows checkout).
find "$PKG" -type d -exec chmod 0755 {} +
find "$PKG/opt" -type f -exec chmod 0644 {} +
chmod 0755 "$PKG/opt/tracknet-prepper/tracknet-prepper" "$PKG/opt/tracknet-prepper/tracknet-prepper-cli"
find "$PKG/opt" -type f \( -name '*.so' -o -name '*.so.*' \) -exec chmod 0755 {} +
chmod 0755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm" "$PKG/usr/bin/"*

desktop-file-validate "$PKG/usr/share/applications/tracknet-prepper.desktop"

mkdir -p "$OUT"
DEB="$OUT/tracknet-prepper_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$DEB"
dpkg-deb --info "$DEB" | sed -n '1,30p'

step "Checksums"
( cd "$OUT" && sha256sum "$(basename "$DEB")" | tee SHA256SUMS-linux.txt )
ls -la "$OUT"
echo "Done: $DEB"
