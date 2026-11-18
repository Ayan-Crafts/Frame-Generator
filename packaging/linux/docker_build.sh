#!/usr/bin/env bash
# Build the Ubuntu 24.04 .deb in a throwaway ubuntu:24.04 container.
#   bash packaging/linux/docker_build.sh            # with tests
#   SKIP_TESTS=1 bash packaging/linux/docker_build.sh
#   USE_GPU=1 bash packaging/linux/docker_build.sh  # also run the GPU tests
#                                                   # (needs the NVIDIA container runtime)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GPU_ARGS=()
if [ "${USE_GPU:-0}" = 1 ]; then
  # The "video" capability exposes libnvcuvid (NVDEC) and libnvidia-encode;
  # Docker's default capabilities (compute,utility) do not include them.
  GPU_ARGS=(--gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video)
fi
docker run --rm "${GPU_ARGS[@]}" -v "$ROOT:/src" -e SRC=/src -e OUT=/src/release \
  -e SKIP_TESTS="${SKIP_TESTS:-0}" ubuntu:24.04 bash /src/packaging/linux/build_linux.sh
